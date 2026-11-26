"""Hardware node ingest router, node seeding, and IST hourly/daily aggregation."""
import asyncio
import hashlib
import hmac
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, field_validator
from pymongo import UpdateOne
from pymongo.errors import DuplicateKeyError

from aqi_data import (
    STATIONS,
    aqi_cpcb,
    category_for_aqi,
    current_reading as synth_current_reading,
    history_24h as synth_history_24h,
)

logger = logging.getLogger(__name__)

TTL_90_DAYS_SECONDS = 90 * 24 * 60 * 60
AGGREGATION_INTERVAL_SECONDS = 10 * 60
ONLINE_WINDOW = timedelta(minutes=5)
IST = timezone(timedelta(hours=5, minutes=30))
IST_TZ_NAME = "Asia/Kolkata"
MIN_COVERED_HOURS_PER_DAY = 12


class IngestReadingIn(BaseModel):
    node_id: str = Field(min_length=1, max_length=64)
    boot_id: int = Field(default=0, ge=0)
    seq: int = Field(ge=0)
    ts: Optional[datetime] = None
    pm1: Optional[float] = Field(default=None, ge=0.0, le=2000.0, allow_inf_nan=False)
    pm25: Optional[float] = Field(default=None, ge=0.0, le=2000.0, allow_inf_nan=False)
    pm10: Optional[float] = Field(default=None, ge=0.0, le=2000.0, allow_inf_nan=False)
    pm_samples: Optional[int] = Field(default=None, ge=0)
    temp_c: Optional[float] = Field(default=None, ge=-20.0, le=60.0, allow_inf_nan=False)
    rh_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0, allow_inf_nan=False)
    gas_sensor: str = Field(default="MQ2", min_length=1, max_length=32)
    gas_alarm: bool = False
    gas_alarm_frac: float = Field(default=0.0, ge=0.0, le=1.0, allow_inf_nan=False)
    gas_mv: Optional[float] = Field(default=None, ge=0.0, le=5000.0, allow_inf_nan=False)
    warmup: bool = False
    rssi: Optional[int] = Field(default=None, ge=-150, le=20)
    fw: str = Field(default="0.1.0", min_length=1, max_length=32)
    # Optional legacy fields kept so older simulators still validate cleanly
    mq135_mv: Optional[float] = Field(default=None, ge=0.0, le=5000.0, allow_inf_nan=False)
    mq135_rs_r0: Optional[float] = Field(default=None, ge=0.0, allow_inf_nan=False)

    @field_validator("boot_id", mode="before")
    @classmethod
    def _default_boot_id(cls, value: Any) -> int:
        return 0 if value is None else value


def hash_node_key(raw_key: str) -> str:
    """Return SHA-256 hex digest of a node's API key."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _opt_float(val: Any) -> Optional[float]:
    return float(val) if val is not None else None


def _opt_round(val: Any, digits: int = 1) -> Optional[float]:
    return round(float(val), digits) if val is not None else None


def _station_coords(station_id: str) -> tuple[float, float]:
    for s in STATIONS:
        if s["id"] == station_id:
            return float(s["lat"]), float(s["lng"])
    return 30.3540, 76.3680


async def ensure_ingest_indexes(db: Any) -> None:
    await db.nodes.create_index("node_id", unique=True)

    # Drop legacy (node_id, seq) unique index before creating (node_id, boot_id, seq).
    existing = await db.readings_raw.index_information()
    for idx_name, idx_meta in existing.items():
        if idx_meta.get("key") == [("node_id", 1), ("seq", 1)]:
            await db.readings_raw.drop_index(idx_name)
            logger.info("Dropped legacy readings_raw index: %s", idx_name)

    await db.readings_raw.update_many(
        {"boot_id": {"$exists": False}},
        {"$set": {"boot_id": 0}},
    )
    await db.readings_raw.create_index(
        [("node_id", 1), ("boot_id", 1), ("seq", 1)],
        unique=True,
    )
    await db.readings_raw.create_index([("node_id", 1), ("ts", -1)])
    await db.readings_raw.create_index("received_at", expireAfterSeconds=TTL_90_DAYS_SECONDS)
    await db.readings_hourly.create_index([("node_id", 1), ("hour", 1)], unique=True)
    await db.readings_daily.create_index([("node_id", 1), ("date", 1)], unique=True)


async def seed_default_node(db: Any) -> None:
    node_key = (os.environ.get("NODE_API_KEY") or "").strip()
    if not node_key:
        logger.warning("NODE_API_KEY not set; skipping default node airaura-01 seed")
        return

    lat, lng = _station_coords("thapar-campus")
    key_hash = hash_node_key(node_key)
    existing = await db.nodes.find_one({"node_id": "airaura-01"})
    if existing is None:
        await db.nodes.insert_one({
            "node_id": "airaura-01",
            "name": "AirAura Node 01",
            "station_id": "thapar-campus",
            "lat": lat,
            "lng": lng,
            "key_hash": key_hash,
            "mq135_r0": None,
            "last_seen": None,
        })
        logger.info("Seeded default node: airaura-01")
    elif existing.get("key_hash") != key_hash:
        await db.nodes.update_one(
            {"node_id": "airaura-01"},
            {"$set": {"key_hash": key_hash}},
        )
        logger.info("Updated key_hash for node: airaura-01")


async def clear_fake_node_data(db: Any, node_id: str = "airaura-01") -> dict[str, int]:
    """Remove simulator readings for a node (fw starting with 'fake' or missing boot_id)."""
    raw_filter = {
        "node_id": node_id,
        "$or": [
            {"fw": {"$regex": "^fake"}},
            {"boot_id": {"$exists": False}},
            {"boot_id": None},
        ],
    }
    raw_res = await db.readings_raw.delete_many(raw_filter)
    remaining_real = await db.readings_raw.count_documents({"node_id": node_id})
    hourly_deleted = 0
    daily_deleted = 0
    if remaining_real == 0:
        hourly_deleted = (await db.readings_hourly.delete_many({"node_id": node_id})).deleted_count
        daily_deleted = (await db.readings_daily.delete_many({"node_id": node_id})).deleted_count
        await db.nodes.update_one({"node_id": node_id}, {"$set": {"last_seen": None}})
    return {
        "raw_deleted": raw_res.deleted_count,
        "hourly_deleted": hourly_deleted,
        "daily_deleted": daily_deleted,
        "remaining_real": remaining_real,
    }


async def _aggregate_hourly(db: Any, since: Optional[datetime], now: datetime) -> int:
    match: dict[str, Any] = {"warmup": {"$ne": True}}
    if since is not None:
        match["ts"] = {"$gte": since}
    pipeline = [
        {"$match": match},
        {
            "$group": {
                "_id": {
                    "node_id": "$node_id",
                    "hour": {"$dateTrunc": {"date": "$ts", "unit": "hour", "timezone": IST_TZ_NAME}},
                },
                "pm1": {"$avg": "$pm1"},
                "pm25": {"$avg": "$pm25"},
                "pm10": {"$avg": "$pm10"},
                "temp_c": {"$avg": "$temp_c"},
                "rh_pct": {"$avg": "$rh_pct"},
                "gas_alarm_frac": {"$avg": "$gas_alarm_frac"},
                "gas_mv": {"$avg": "$gas_mv"},
                "mq135_rs_r0": {"$avg": "$mq135_rs_r0"},
                "count": {"$sum": 1},
            }
        },
    ]
    ops = []
    async for row in db.readings_raw.aggregate(pipeline):
        node_id = row["_id"]["node_id"]
        hour_val = row["_id"]["hour"]
        doc = {
            "node_id": node_id,
            "hour": hour_val,
            "pm1": _opt_round(row.get("pm1"), 2),
            "pm25": _opt_round(row.get("pm25"), 2),
            "pm10": _opt_round(row.get("pm10"), 2),
            "temp_c": _opt_round(row.get("temp_c"), 2),
            "rh_pct": _opt_round(row.get("rh_pct"), 2),
            "gas_alarm_frac": _opt_round(row.get("gas_alarm_frac"), 3),
            "gas_mv": _opt_round(row.get("gas_mv"), 1),
            "mq135_rs_r0": _opt_round(row.get("mq135_rs_r0"), 3),
            "count": int(row["count"]),
            "updated_at": now,
        }
        ops.append(
            UpdateOne(
                {"node_id": node_id, "hour": hour_val},
                {"$set": doc},
                upsert=True,
            )
        )
    if not ops:
        return 0
    await db.readings_hourly.bulk_write(ops, ordered=False)
    return len(ops)


async def _covered_hours_by_day(db: Any, since: Optional[datetime]) -> dict[tuple[str, str], int]:
    match: dict[str, Any] = {"pm25": {"$ne": None}, "pm10": {"$ne": None}}
    if since is not None:
        match["hour"] = {"$gte": since}
    pipeline = [
        {"$match": match},
        {
            "$group": {
                "_id": {
                    "node_id": "$node_id",
                    "date": {"$dateToString": {"format": "%Y-%m-%d", "date": "$hour", "timezone": IST_TZ_NAME}},
                },
                "covered_hours": {"$sum": 1},
            }
        },
    ]
    out: dict[tuple[str, str], int] = {}
    async for row in db.readings_hourly.aggregate(pipeline):
        out[(row["_id"]["node_id"], row["_id"]["date"])] = int(row["covered_hours"])
    return out


async def _aggregate_daily(db: Any, since: Optional[datetime], now: datetime) -> int:
    match: dict[str, Any] = {"warmup": {"$ne": True}}
    if since is not None:
        match["ts"] = {"$gte": since}
    covered_map = await _covered_hours_by_day(db, since)
    pipeline = [
        {"$match": match},
        {
            "$group": {
                "_id": {
                    "node_id": "$node_id",
                    "date": {"$dateToString": {"format": "%Y-%m-%d", "date": "$ts", "timezone": IST_TZ_NAME}},
                },
                "pm1": {"$avg": "$pm1"},
                "pm25": {"$avg": "$pm25"},
                "pm10": {"$avg": "$pm10"},
                "temp_c": {"$avg": "$temp_c"},
                "rh_pct": {"$avg": "$rh_pct"},
                "gas_alarm_frac": {"$avg": "$gas_alarm_frac"},
                "gas_mv": {"$avg": "$gas_mv"},
                "mq135_rs_r0": {"$avg": "$mq135_rs_r0"},
                "count": {"$sum": 1},
            }
        },
    ]
    ops = []
    async for row in db.readings_raw.aggregate(pipeline):
        node_id = row["_id"]["node_id"]
        date_val = row["_id"]["date"]
        doc = {
            "node_id": node_id,
            "date": date_val,
            "pm1": _opt_round(row.get("pm1"), 2),
            "pm25": _opt_round(row.get("pm25"), 2),
            "pm10": _opt_round(row.get("pm10"), 2),
            "temp_c": _opt_round(row.get("temp_c"), 2),
            "rh_pct": _opt_round(row.get("rh_pct"), 2),
            "gas_alarm_frac": _opt_round(row.get("gas_alarm_frac"), 3),
            "gas_mv": _opt_round(row.get("gas_mv"), 1),
            "mq135_rs_r0": _opt_round(row.get("mq135_rs_r0"), 3),
            "count": int(row["count"]),
            "covered_hours": covered_map.get((node_id, date_val), 0),
            "updated_at": now,
        }
        ops.append(
            UpdateOne(
                {"node_id": node_id, "date": date_val},
                {"$set": doc},
                upsert=True,
            )
        )
    if not ops:
        return 0
    await db.readings_daily.bulk_write(ops, ordered=False)
    return len(ops)


async def aggregate_readings(db: Any, full: bool = False) -> dict[str, Any]:
    """Aggregate readings_raw into IST hourly/daily collections (last 48h unless full=True)."""
    now = datetime.now(timezone.utc)
    if full:
        hourly_since = None
        daily_since = None
    else:
        hourly_since = (now - timedelta(hours=48)).replace(minute=0, second=0, microsecond=0)
        ist_cutoff = (now.astimezone(IST) - timedelta(hours=48)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        daily_since = ist_cutoff.astimezone(timezone.utc)

    hourly_count = await _aggregate_hourly(db, hourly_since, now)
    daily_count = await _aggregate_daily(db, daily_since, now)
    return {"hourly_buckets": hourly_count, "daily_buckets": daily_count, "full": full}


async def get_node_for_station(db: Any, station_id: str) -> Optional[dict]:
    """Return the registered hardware node document for a station, or None."""
    return await db.nodes.find_one({"station_id": station_id}, {"_id": 0, "key_hash": 0})


async def get_nodes_by_station(db: Any) -> dict[str, dict]:
    """Return a station_id -> node mapping across all registered nodes."""
    docs = await db.nodes.find({}, {"_id": 0, "key_hash": 0}).to_list(100)
    return {doc["station_id"]: doc for doc in docs if doc.get("station_id")}


def is_node_online(node: Optional[dict], now: Optional[datetime] = None) -> bool:
    if not node:
        return False
    now = now or datetime.now(timezone.utc)
    last_seen = _ensure_utc(node.get("last_seen"))
    return bool(last_seen is not None and (now - last_seen) < ONLINE_WINDOW)


async def node_has_data(db: Any, node_id: str) -> bool:
    return (await db.readings_raw.find_one({"node_id": node_id}, {"_id": 1})) is not None


async def node_current_reading(
    db: Any,
    node: dict,
    now: Optional[datetime] = None,
) -> Optional[dict]:
    """Build current reading for a node with real data (online, warming_up, or offline)."""
    now = now or datetime.now(timezone.utc)
    node_id = node["node_id"]
    latest_any = await db.readings_raw.find_one(
        {"node_id": node_id},
        {"_id": 0},
        sort=[("ts", -1), ("received_at", -1), ("seq", -1)],
    )
    if latest_any is None:
        return None

    online = is_node_online(node, now)
    last_seen_dt = _ensure_utc(node.get("last_seen"))

    latest_valid = None
    if latest_any.get("warmup"):
        latest_valid = await db.readings_raw.find_one(
            {"node_id": node_id, "warmup": {"$ne": True}},
            {"_id": 0},
            sort=[("ts", -1), ("received_at", -1), ("seq", -1)],
        )
    else:
        latest_valid = latest_any

    base = latest_valid if latest_valid is not None else latest_any
    if not online:
        node_status = "offline"
    elif latest_any.get("warmup"):
        node_status = "warming_up"
    else:
        node_status = "online"

    pm1_val = base.get("pm1")
    pm25_val = base.get("pm25")
    pm10_val = base.get("pm10")
    pm_stale = False
    if pm25_val is None:
        pm_stale = True
        last_pm = await db.readings_raw.find_one(
            {"node_id": node_id, "pm25": {"$ne": None}},
            {"_id": 0},
            sort=[("ts", -1), ("received_at", -1), ("seq", -1)],
        )
        if last_pm is not None:
            pm1_val = last_pm.get("pm1")
            pm25_val = last_pm.get("pm25")
            pm10_val = last_pm.get("pm10")

    anchor = now if online else (_ensure_utc(base["ts"]) or now)
    since_24h = anchor - timedelta(hours=24)
    agg_cursor = db.readings_raw.aggregate([
        {
            "$match": {
                "node_id": node_id,
                "warmup": {"$ne": True},
                "ts": {"$gte": since_24h, "$lte": anchor + timedelta(minutes=5)},
            }
        },
        {
            "$group": {
                "_id": None,
                "pm25": {"$avg": "$pm25"},
                "pm10": {"$avg": "$pm10"},
            }
        },
    ])
    agg_rows = await agg_cursor.to_list(1)
    mean_pm25 = _opt_float(agg_rows[0].get("pm25")) if agg_rows else None
    mean_pm10 = _opt_float(agg_rows[0].get("pm10")) if agg_rows else None
    if mean_pm25 is None:
        mean_pm25 = _opt_float(pm25_val)
    if mean_pm10 is None:
        mean_pm10 = _opt_float(pm10_val)

    if mean_pm25 is not None:
        aqi, dominant = aqi_cpcb(mean_pm25, mean_pm10)
    elif mean_pm10 is not None:
        aqi, dominant = aqi_cpcb(0.0, mean_pm10)
    else:
        aqi, dominant = 0, "PM2.5"

    temp_val = base.get("temp_c")
    rh_val = _opt_round(base.get("rh_pct"), 1)
    gas_sensor = base.get("gas_sensor") or ("MQ-135" if base.get("mq135_rs_r0") is not None else "MQ2")
    gas_mv = _opt_round(base.get("gas_mv"), 1)
    gas_index = _opt_round(base.get("mq135_rs_r0"), 2)

    return {
        "timestamp": _ensure_utc(base["ts"]).isoformat(),
        "pm1": _opt_round(pm1_val, 1),
        "pm25": _opt_round(pm25_val, 1),
        "pm10": _opt_round(pm10_val, 1),
        "pm25_24h": _opt_round(mean_pm25, 1),
        "pm10_24h": _opt_round(mean_pm10, 1),
        "pm_stale": pm_stale,
        "temperature": _opt_round(temp_val, 1),
        "humidity": rh_val,
        "gas_sensor": gas_sensor,
        "gas_alarm": bool(base.get("gas_alarm", False)),
        "gas_alarm_frac": round(float(base.get("gas_alarm_frac", 0.0)), 2),
        "gas_mv": gas_mv,
        "gas_index": gas_index,
        "aqi": aqi,
        "dominant_pollutant": dominant,
        "category": category_for_aqi(aqi),
        "rh_warning": bool(rh_val is not None and rh_val > 75.0),
        "simulated": False,
        "source": "airaura-node",
        "node_status": node_status,
        "stale": node_status == "offline",
        "last_seen": last_seen_dt.isoformat() if last_seen_dt else None,
        "node_id": node_id,
    }


async def resolve_station_current(
    db: Any,
    station: dict,
    node: Optional[dict] = None,
    _node_checked: bool = False,
) -> dict:
    """Return last real node reading if node has data, otherwise synthetic fallback."""
    if not _node_checked:
        node = await get_node_for_station(db, station["id"])

    if node is None:
        reading = synth_current_reading(station)
        reading["node_status"] = None
        return reading

    live = await node_current_reading(db, node)
    if live is not None:
        return live

    # Node has never sent any data yet -> synthetic fallback
    reading = synth_current_reading(station)
    reading["node_status"] = "warming_up" if is_node_online(node) else "offline"
    reading["node_id"] = node["node_id"]
    return reading


async def resolve_station_history_24h(db: Any, station: dict) -> tuple[list[dict], bool, str]:
    """Return 24h hourly history from readings_hourly with 24-h rolling CPCB AQI."""
    node = await get_node_for_station(db, station["id"])
    now = datetime.now(timezone.utc)
    if node is not None and await node_has_data(db, node["node_id"]):
        anchor = now if is_node_online(node, now) else (_ensure_utc(node.get("last_seen")) or now)
        since_48h = anchor - timedelta(hours=48)
        since_24h = anchor - timedelta(hours=24)
        docs = await (
            db.readings_hourly.find(
                {
                    "node_id": node["node_id"],
                    "hour": {"$gte": since_48h, "$lte": anchor + timedelta(hours=1)},
                },
                {"_id": 0},
            )
            .sort("hour", 1)
            .to_list(60)
        )
        hourly_utc = [(_ensure_utc(d["hour"]), d) for d in docs]
        recent = [(h, d) for h, d in hourly_utc if h >= since_24h][-24:]
        if not recent:
            recent = hourly_utc[-24:]
        items = []
        for h_dt, d in recent:
            win_start = h_dt - timedelta(hours=23)
            window = [w for wh, w in hourly_utc if win_start <= wh <= h_dt] or [d]

            pm25_pairs = [
                (float(w["pm25"]), max(1, int(w.get("count", 1))))
                for w in window
                if w.get("pm25") is not None
            ]
            pm10_pairs = [
                (float(w["pm10"]), max(1, int(w.get("count", 1))))
                for w in window
                if w.get("pm10") is not None
            ]
            mean_pm25 = (
                sum(v * wt for v, wt in pm25_pairs) / sum(wt for _, wt in pm25_pairs)
                if pm25_pairs
                else None
            )
            mean_pm10 = (
                sum(v * wt for v, wt in pm10_pairs) / sum(wt for _, wt in pm10_pairs)
                if pm10_pairs
                else None
            )
            if mean_pm25 is not None:
                rolling_aqi, dominant = aqi_cpcb(mean_pm25, mean_pm10)
            elif mean_pm10 is not None:
                rolling_aqi, dominant = aqi_cpcb(0.0, mean_pm10)
            else:
                rolling_aqi, dominant = 0, "PM2.5"

            items.append({
                "timestamp": h_dt.isoformat(),
                "pm1": _opt_round(d.get("pm1"), 1),
                "pm25": _opt_round(d.get("pm25"), 1),
                "pm10": _opt_round(d.get("pm10"), 1),
                "pm25_24h": _opt_round(mean_pm25, 1),
                "pm10_24h": _opt_round(mean_pm10, 1),
                "temperature": _opt_round(d.get("temp_c"), 1),
                "humidity": _opt_round(d.get("rh_pct"), 1),
                "gas_alarm_frac": _opt_round(d.get("gas_alarm_frac"), 2),
                "gas_mv": _opt_round(d.get("gas_mv"), 1),
                "gas_index": _opt_round(d.get("mq135_rs_r0"), 2),
                "aqi": rolling_aqi,
                "dominant_pollutant": dominant,
                "category": category_for_aqi(rolling_aqi),
                "count": int(d.get("count", 0)),
                "simulated": False,
                "source": "airaura-node",
            })
        return items, False, "airaura-node"

    return synth_history_24h(station, now=now), True, "simulated"


async def resolve_station_daily_for_predict(db: Any, node: dict) -> dict[str, Any]:
    """Validate >=12h daily coverage and 8 consecutive IST days for ML prediction."""
    node_id = node["node_id"]
    now_ist = datetime.now(IST)
    today_date = now_ist.date()
    yesterday_date = today_date - timedelta(days=1)
    today_str = today_date.isoformat()

    docs = await (
        db.readings_daily.find({"node_id": node_id}, {"_id": 0})
        .sort("date", 1)
        .to_list(365)
    )
    covered_map = await _covered_hours_by_day(db, since=None)

    covered_rows = []
    for d in docs:
        d_str = d.get("date")
        if not d_str or d_str > today_str:
            continue
        if d.get("pm25") is None or d.get("pm10") is None:
            continue
        cov = d.get("covered_hours")
        if cov is None:
            cov = covered_map.get((node_id, d_str), 0)
        if int(cov) < MIN_COVERED_HOURS_PER_DAY:
            continue
        covered_rows.append({
            "date": d_str,
            "date_obj": date.fromisoformat(d_str),
            "pm25": float(d["pm25"]),
            "pm10": float(d["pm10"]),
            "covered_hours": int(cov),
        })

    # Compute trailing consecutive covered day streak
    streak = 0
    has_gap = False
    if covered_rows:
        # If today isn't covered, latest eligible day is yesterday
        latest_obj = covered_rows[-1]["date_obj"]
        if latest_obj < yesterday_date:
            has_gap = True
            streak = 0
        else:
            streak = 1
            for i in range(len(covered_rows) - 1, 0, -1):
                if (covered_rows[i]["date_obj"] - covered_rows[i - 1]["date_obj"]).days == 1:
                    streak += 1
                else:
                    has_gap = True
                    break

    if streak >= 8:
        window = covered_rows[-8:]
        return {
            "ready": True,
            "daily": window,
            "latest_date": window[-1]["date_obj"],
        }

    resp: dict[str, Any] = {
        "ready": False,
        "days_available": streak,
        "days_needed": 8,
    }
    if has_gap:
        resp["reason"] = "gap in data"
    return resp


async def aggregation_loop(db: Any, interval_seconds: int = AGGREGATION_INTERVAL_SECONDS) -> None:
    """Periodically aggregate the last 48h of readings_raw into hourly and daily collections."""
    while True:
        try:
            res = await aggregate_readings(db, full=False)
            logger.info("Periodic aggregation complete: %s", res)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Periodic aggregation failed")
        await asyncio.sleep(interval_seconds)


def _require_node_key(
    x_node_key: Optional[str] = Header(default=None, alias="X-Node-Key"),
) -> str:
    cleaned = (x_node_key or "").strip()
    if not cleaned:
        raise HTTPException(status_code=401, detail="Missing X-Node-Key header")
    return cleaned


def create_ingest_router(db: Any, require_role: Callable[..., Any]) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["ingest"])

    @router.post("/ingest")
    async def ingest_reading(
        data: IngestReadingIn,
        x_node_key: str = Depends(_require_node_key),
    ):
        node = await db.nodes.find_one({"node_id": data.node_id})
        expected_hash = node.get("key_hash", "") if node else ""
        if node is None or not hmac.compare_digest(hash_node_key(x_node_key), expected_hash):
            raise HTTPException(status_code=401, detail="Invalid node credentials")

        now = datetime.now(timezone.utc)
        ts_corrected = False
        if data.ts is None:
            ts_dt = now
            ts_corrected = True
        else:
            candidate = _ensure_utc(data.ts)
            if candidate > now + timedelta(minutes=5) or candidate < now - timedelta(days=7):
                ts_dt = now
                ts_corrected = True
            else:
                ts_dt = candidate

        doc = {
            "node_id": data.node_id,
            "boot_id": int(data.boot_id),
            "seq": int(data.seq),
            "ts": ts_dt,
            "ts_corrected": ts_corrected,
            "received_at": now,
            "pm1": _opt_float(data.pm1),
            "pm25": _opt_float(data.pm25),
            "pm10": _opt_float(data.pm10),
            "pm_samples": data.pm_samples,
            "temp_c": _opt_float(data.temp_c),
            "rh_pct": _opt_float(data.rh_pct),
            "gas_sensor": data.gas_sensor,
            "gas_alarm": bool(data.gas_alarm),
            "gas_alarm_frac": float(data.gas_alarm_frac),
            "gas_mv": _opt_float(data.gas_mv),
            "mq135_mv": _opt_float(data.mq135_mv),
            "mq135_rs_r0": _opt_float(data.mq135_rs_r0),
            "warmup": bool(data.warmup),
            "rssi": data.rssi,
            "fw": data.fw,
        }

        try:
            await db.readings_raw.insert_one(doc)
        except DuplicateKeyError:
            return {
                "status": "ok",
                "duplicate": True,
                "node_id": data.node_id,
                "boot_id": data.boot_id,
                "seq": data.seq,
            }

        await db.nodes.update_one(
            {"node_id": data.node_id},
            {"$set": {"last_seen": now}},
        )
        return {
            "status": "ok",
            "duplicate": False,
            "node_id": data.node_id,
            "boot_id": data.boot_id,
            "seq": data.seq,
            "ts": ts_dt.isoformat(),
            "ts_corrected": ts_corrected,
        }

    @router.post("/admin/aggregate")
    async def trigger_aggregation(
        full: bool = False,
        user: dict = Depends(require_role("pcb_official")),
    ):
        summary = await aggregate_readings(db, full=full)
        return {"status": "ok", **summary}

    @router.get("/nodes/{node_id}/status")
    async def node_status(node_id: str):
        node = await db.nodes.find_one({"node_id": node_id}, {"_id": 0, "key_hash": 0})
        if node is None:
            raise HTTPException(status_code=404, detail="Node not found")

        last_seen = _ensure_utc(node.get("last_seen"))
        online = bool(
            last_seen is not None and (datetime.now(timezone.utc) - last_seen) < ONLINE_WINDOW
        )
        days_of_daily_data = await db.readings_daily.count_documents({"node_id": node_id})
        covered_days = await db.readings_daily.count_documents({
            "node_id": node_id,
            "covered_hours": {"$gte": MIN_COVERED_HOURS_PER_DAY},
        })

        latest = await db.readings_raw.find_one(
            {"node_id": node_id},
            {"_id": 0},
            sort=[("ts", -1), ("received_at", -1), ("seq", -1)],
        )
        if latest is not None:
            if isinstance(latest.get("ts"), datetime):
                latest["ts"] = _ensure_utc(latest["ts"]).isoformat()
            if isinstance(latest.get("received_at"), datetime):
                latest["received_at"] = _ensure_utc(latest["received_at"]).isoformat()

        return {
            "node_id": node["node_id"],
            "name": node.get("name"),
            "station_id": node.get("station_id"),
            "lat": node.get("lat"),
            "lng": node.get("lng"),
            "mq135_r0": node.get("mq135_r0"),
            "last_seen": last_seen.isoformat() if last_seen else None,
            "online": online,
            "days_of_daily_data": days_of_daily_data,
            "covered_days_of_daily_data": covered_days,
            "latest": latest,
        }

    return router
