"""Hardware node ingest router, node seeding, and hourly/daily aggregation."""
import asyncio
import hashlib
import hmac
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
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


class IngestReadingIn(BaseModel):
    node_id: str = Field(min_length=1, max_length=64)
    ts: Optional[datetime] = None
    seq: int = Field(ge=0)
    pm25: float = Field(ge=0.0, le=2000.0, allow_inf_nan=False)
    pm10: float = Field(ge=0.0, le=2000.0, allow_inf_nan=False)
    mq135_mv: float = Field(ge=0.0, le=5000.0, allow_inf_nan=False)
    mq135_rs_r0: float = Field(ge=0.0, allow_inf_nan=False)
    temp_c: float = Field(ge=-20.0, le=60.0, allow_inf_nan=False)
    rh_pct: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    warmup: bool = False
    fw: str = Field(default="0.1.0", min_length=1, max_length=32)


def hash_node_key(raw_key: str) -> str:
    """Return SHA-256 hex digest of a node's API key."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _station_coords(station_id: str) -> tuple[float, float]:
    for s in STATIONS:
        if s["id"] == station_id:
            return float(s["lat"]), float(s["lng"])
    return 30.3540, 76.3680


async def ensure_ingest_indexes(db: Any) -> None:
    await db.nodes.create_index("node_id", unique=True)
    await db.readings_raw.create_index([("node_id", 1), ("seq", 1)], unique=True)
    await db.readings_raw.create_index([("node_id", 1), ("ts", -1)])
    await db.readings_raw.create_index("received_at", expireAfterSeconds=TTL_90_DAYS_SECONDS)
    await db.readings_hourly.create_index([("node_id", 1), ("hour", 1)], unique=True)
    await db.readings_daily.create_index([("node_id", 1), ("date", 1)], unique=True)


async def seed_default_node(db: Any) -> None:
    node_key = os.environ.get("NODE_API_KEY")
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


async def _aggregate_granularity(
    db: Any,
    bucket_expr: dict[str, Any],
    target_collection: Any,
    bucket_field: str,
    now: datetime,
) -> int:
    pipeline = [
        {"$match": {"warmup": {"$ne": True}}},
        {
            "$group": {
                "_id": {"node_id": "$node_id", "bucket": bucket_expr},
                "pm25": {"$avg": "$pm25"},
                "pm10": {"$avg": "$pm10"},
                "mq135_rs_r0": {"$avg": "$mq135_rs_r0"},
                "temp_c": {"$avg": "$temp_c"},
                "rh_pct": {"$avg": "$rh_pct"},
                "count": {"$sum": 1},
            }
        },
    ]
    ops = []
    async for row in db.readings_raw.aggregate(pipeline):
        node_id = row["_id"]["node_id"]
        bucket_val = row["_id"]["bucket"]
        doc = {
            "node_id": node_id,
            bucket_field: bucket_val,
            "pm25": round(float(row["pm25"]), 2),
            "pm10": round(float(row["pm10"]), 2),
            "mq135_rs_r0": round(float(row["mq135_rs_r0"]), 3),
            "temp_c": round(float(row["temp_c"]), 2),
            "rh_pct": round(float(row["rh_pct"]), 2),
            "count": int(row["count"]),
            "updated_at": now,
        }
        ops.append(
            UpdateOne(
                {"node_id": node_id, bucket_field: bucket_val},
                {"$set": doc},
                upsert=True,
            )
        )
    if not ops:
        return 0
    await target_collection.bulk_write(ops, ordered=False)
    return len(ops)


async def aggregate_readings(db: Any) -> dict[str, int]:
    """Build readings_hourly and readings_daily means from readings_raw (excluding warmup)."""
    now = datetime.now(timezone.utc)
    hourly_count = await _aggregate_granularity(
        db,
        {"$dateTrunc": {"date": "$ts", "unit": "hour", "timezone": "UTC"}},
        db.readings_hourly,
        "hour",
        now,
    )
    daily_count = await _aggregate_granularity(
        db,
        {"$dateToString": {"format": "%Y-%m-%d", "date": "$ts", "timezone": "UTC"}},
        db.readings_daily,
        "date",
        now,
    )
    return {"hourly_buckets": hourly_count, "daily_buckets": daily_count}


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


async def node_current_reading(
    db: Any,
    node: dict,
    now: Optional[datetime] = None,
) -> Optional[dict]:
    """Build current reading for an online node using 24h rolling CPCB AQI."""
    now = now or datetime.now(timezone.utc)
    if not is_node_online(node, now):
        return None

    node_id = node["node_id"]
    latest_any = await db.readings_raw.find_one(
        {"node_id": node_id},
        {"_id": 0},
        sort=[("ts", -1), ("seq", -1)],
    )
    if latest_any is None:
        return None

    if latest_any.get("warmup"):
        latest_valid = await db.readings_raw.find_one(
            {"node_id": node_id, "warmup": {"$ne": True}},
            {"_id": 0},
            sort=[("ts", -1), ("seq", -1)],
        )
        if latest_valid is None:
            return None
        node_status = "warming_up"
    else:
        latest_valid = latest_any
        node_status = "online"

    since_24h = now - timedelta(hours=24)
    agg_cursor = db.readings_raw.aggregate([
        {
            "$match": {
                "node_id": node_id,
                "warmup": {"$ne": True},
                "ts": {"$gte": since_24h},
            }
        },
        {
            "$group": {
                "_id": None,
                "pm25": {"$avg": "$pm25"},
                "pm10": {"$avg": "$pm10"},
                "count": {"$sum": 1},
            }
        },
    ])
    agg_rows = await agg_cursor.to_list(1)
    if agg_rows and agg_rows[0].get("count", 0) > 0:
        mean_pm25 = float(agg_rows[0]["pm25"])
        mean_pm10 = float(agg_rows[0]["pm10"])
    else:
        mean_pm25 = float(latest_valid["pm25"])
        mean_pm10 = float(latest_valid["pm10"])

    aqi, dominant = aqi_cpcb(mean_pm25, mean_pm10)
    rh = round(float(latest_valid["rh_pct"]), 1)
    return {
        "timestamp": _ensure_utc(latest_valid["ts"]).isoformat(),
        "pm25": round(float(latest_valid["pm25"]), 1),
        "pm10": round(float(latest_valid["pm10"]), 1),
        "temperature": round(float(latest_valid["temp_c"]), 1),
        "humidity": rh,
        "gas_index": round(float(latest_valid["mq135_rs_r0"]), 2),
        "aqi": aqi,
        "dominant_pollutant": dominant,
        "category": category_for_aqi(aqi),
        "rh_warning": rh > 75.0,
        "simulated": False,
        "source": "airaura-node",
        "node_status": node_status,
        "node_id": node_id,
    }


async def resolve_station_current(
    db: Any,
    station: dict,
    node: Optional[dict] = None,
    _node_checked: bool = False,
) -> dict:
    """Return live node reading when online and valid, otherwise synthetic fallback."""
    if not _node_checked:
        node = await get_node_for_station(db, station["id"])

    if node is None:
        reading = synth_current_reading(station)
        reading["node_status"] = None
        return reading

    live = await node_current_reading(db, node)
    if live is not None:
        return live

    reading = synth_current_reading(station)
    reading["node_status"] = "warming_up" if is_node_online(node) else "offline"
    reading["node_id"] = node["node_id"]
    return reading


async def resolve_station_history_24h(db: Any, station: dict) -> tuple[list[dict], bool, str]:
    """Return 24h hourly history from readings_hourly for online nodes, else synthetic."""
    node = await get_node_for_station(db, station["id"])
    now = datetime.now(timezone.utc)
    if node is not None and is_node_online(node, now):
        since_24h = now - timedelta(hours=24)
        docs = await (
            db.readings_hourly.find(
                {"node_id": node["node_id"], "hour": {"$gte": since_24h}},
                {"_id": 0},
            )
            .sort("hour", 1)
            .to_list(48)
        )
        if docs:
            items = []
            for d in docs[-24:]:
                pm25 = round(float(d["pm25"]), 1)
                pm10 = round(float(d["pm10"]), 1)
                aqi, dominant = aqi_cpcb(pm25, pm10)
                items.append({
                    "timestamp": _ensure_utc(d["hour"]).isoformat(),
                    "pm25": pm25,
                    "pm10": pm10,
                    "temperature": round(float(d["temp_c"]), 1),
                    "humidity": round(float(d["rh_pct"]), 1),
                    "gas_index": round(float(d["mq135_rs_r0"]), 2),
                    "aqi": aqi,
                    "dominant_pollutant": dominant,
                    "category": category_for_aqi(aqi),
                    "count": int(d.get("count", 0)),
                    "simulated": False,
                    "source": "airaura-node",
                })
            return items, False, "airaura-node"

    return synth_history_24h(station, now=now), True, "simulated"


async def resolve_station_daily(db: Any, node: dict, limit: int = 14) -> list[dict]:
    """Return oldest-first daily mean rows from readings_daily for ML feature building."""
    docs = await (
        db.readings_daily.find({"node_id": node["node_id"]}, {"_id": 0})
        .sort("date", 1)
        .to_list(365)
    )
    rows = [
        {
            "date": d["date"],
            "pm25": float(d["pm25"]),
            "pm10": float(d["pm10"]),
            "count": int(d.get("count", 0)),
        }
        for d in docs
    ]
    return rows[-limit:] if limit > 0 else rows


async def aggregation_loop(db: Any, interval_seconds: int = AGGREGATION_INTERVAL_SECONDS) -> None:
    """Periodically aggregate readings_raw into hourly and daily collections."""
    while True:
        try:
            res = await aggregate_readings(db)
            logger.info("Periodic aggregation complete: %s", res)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Periodic aggregation failed")
        await asyncio.sleep(interval_seconds)


def _require_node_key(
    x_node_key: Optional[str] = Header(default=None, alias="X-Node-Key"),
) -> str:
    if not x_node_key:
        raise HTTPException(status_code=401, detail="Missing X-Node-Key header")
    return x_node_key


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
        ts_dt = _ensure_utc(data.ts) if data.ts is not None else now
        doc = {
            "node_id": data.node_id,
            "ts": ts_dt,
            "received_at": now,
            "seq": data.seq,
            "pm25": float(data.pm25),
            "pm10": float(data.pm10),
            "mq135_mv": float(data.mq135_mv),
            "mq135_rs_r0": float(data.mq135_rs_r0),
            "temp_c": float(data.temp_c),
            "rh_pct": float(data.rh_pct),
            "warmup": bool(data.warmup),
            "fw": data.fw,
        }

        try:
            await db.readings_raw.insert_one(doc)
        except DuplicateKeyError:
            return {
                "status": "ok",
                "duplicate": True,
                "node_id": data.node_id,
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
            "seq": data.seq,
            "ts": ts_dt.isoformat(),
        }

    @router.post("/admin/aggregate")
    async def trigger_aggregation(user: dict = Depends(require_role("pcb_official"))):
        summary = await aggregate_readings(db)
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

        latest = await db.readings_raw.find_one(
            {"node_id": node_id},
            {"_id": 0},
            sort=[("ts", -1), ("seq", -1)],
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
            "latest": latest,
        }

    return router
