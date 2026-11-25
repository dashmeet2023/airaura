"""Fake ESP32 AirAura node simulator for testing /api/ingest and aggregation.

Uses only Python stdlib + requests. Sends v0.2.0 firmware payload format.
"""
import argparse
import math
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

IST = timezone(timedelta(hours=5, minutes=30))
FW_VERSION = "fake-0.2.0"


def _clamp(val: float, low: float, high: float) -> float:
    return max(low, min(high, val))


def _default_node_key() -> str:
    if os.environ.get("NODE_API_KEY"):
        return os.environ["NODE_API_KEY"]
    env_path = Path(__file__).resolve().parent.parent / "backend" / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == "NODE_API_KEY" and v.strip():
                return v.strip().strip('"').strip("'")
    return "airaura-node-01-secret"


def generate_reading(
    node_id: str,
    ts: datetime,
    boot_id: int,
    seq: int,
    warmup: bool,
    rng: random.Random,
    gas_sensor: str = "MQ2",
    fw: str = FW_VERSION,
) -> dict:
    """Generate one realistic Patiala winter sensor reading in v0.2.0 payload format."""
    local_ts = ts.astimezone(IST)
    hour = local_ts.hour + local_ts.minute / 60.0

    # Bimodal diurnal PM2.5 curve (peaks ~08:30 and ~21:00 IST), within 40-200 ug/m3.
    morning_peak = math.exp(-((hour - 8.5) ** 2) / (2 * 2.2 ** 2))
    evening_peak = math.exp(-((hour - 21.0) ** 2) / (2 * 2.6 ** 2))
    diurnal = 0.55 * morning_peak + 0.95 * evening_peak
    pm25_raw = _clamp(45.0 + 135.0 * diurnal + rng.uniform(-12.0, 15.0), 40.0, 200.0)
    pm1 = round(pm25_raw * rng.uniform(0.62, 0.78), 1)
    pm10 = round(pm25_raw * rng.uniform(1.5, 1.9), 1)
    pm25 = round(pm25_raw, 1)

    # Patiala winter temperature: ~7 C at night (~03:00 IST) to ~22 C mid-afternoon (~15:00 IST).
    temp_wave = 0.5 * (1.0 + math.sin(2.0 * math.pi * (hour - 9.0) / 24.0))
    temp_c = round(_clamp(7.0 + 15.0 * temp_wave + rng.uniform(-0.6, 0.6), 6.5, 22.5), 1)

    # Winter relative humidity: higher at night (up to 95%), ~50% mid-afternoon.
    rh_base = 94.5 - ((temp_c - 7.0) / 15.0) * 44.5
    rh_pct = round(_clamp(rh_base + rng.uniform(-2.5, 3.0), 40.0, 95.0), 1)

    gas_alarm = pm25 > 185.0
    gas_alarm_frac = round(rng.uniform(0.55, 0.95) if gas_alarm else 0.0, 2)

    return {
        "node_id": node_id,
        "boot_id": boot_id,
        "seq": seq,
        "ts": ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pm1": pm1,
        "pm25": pm25,
        "pm10": pm10,
        "pm_samples": rng.randint(52, 60),
        "temp_c": temp_c,
        "rh_pct": rh_pct,
        "gas_sensor": gas_sensor,
        "gas_alarm": gas_alarm,
        "gas_alarm_frac": gas_alarm_frac,
        "gas_mv": None,
        "warmup": warmup,
        "rssi": rng.randint(-75, -45),
        "fw": fw,
    }


def post_reading(session: requests.Session, base_url: str, key: str, payload: dict) -> dict:
    resp = session.post(
        f"{base_url}/api/ingest",
        json=payload,
        headers={"X-Node-Key": key},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def run_backfill(
    session: requests.Session,
    base_url: str,
    key: str,
    node_id: str,
    days: int,
    admin_email: str,
    admin_password: str,
    gas_sensor: str,
) -> None:
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    total = days * 24 * 6  # 10-minute intervals
    start_ts = now - timedelta(minutes=10 * total)
    rng = random.Random(f"{node_id}-backfill-{days}")
    boot_id = rng.randint(100000, 2**32 - 1)

    inserted = 0
    duplicates = 0
    for i in range(total):
        ts = start_ts + timedelta(minutes=10 * i)
        payload = generate_reading(
            node_id=node_id,
            ts=ts,
            boot_id=boot_id,
            seq=i,
            warmup=(i < 3),
            rng=rng,
            gas_sensor=gas_sensor,
        )
        res = post_reading(session, base_url, key, payload)
        if res.get("duplicate"):
            duplicates += 1
        else:
            inserted += 1

    print(
        f"Backfilled {total} readings ({days} days @ 10m) for {node_id} (boot_id={boot_id}): "
        f"inserted={inserted}, duplicates={duplicates}"
    )

    login_resp = session.post(
        f"{base_url}/api/auth/login",
        json={"email": admin_email, "password": admin_password},
        timeout=10,
    )
    login_resp.raise_for_status()
    token = login_resp.json()["token"]

    agg_resp = session.post(
        f"{base_url}/api/admin/aggregate?full=true",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    agg_resp.raise_for_status()
    print("Aggregation triggered:", agg_resp.json())


def run_live(
    session: requests.Session,
    base_url: str,
    key: str,
    node_id: str,
    interval: float,
    count: int,
    gas_sensor: str,
) -> None:
    rng = random.Random()
    boot_id = rng.randint(100000, 2**32 - 1)
    seq = 0
    print(f"Starting live simulator for {node_id} -> {base_url} (boot_id={boot_id}, interval={interval}s)")
    try:
        while count <= 0 or seq < count:
            now = datetime.now(timezone.utc)
            payload = generate_reading(
                node_id=node_id,
                ts=now,
                boot_id=boot_id,
                seq=seq,
                warmup=(seq < 3),
                rng=rng,
                gas_sensor=gas_sensor,
            )
            res = post_reading(session, base_url, key, payload)
            print(
                f"[{seq + 1}] boot={boot_id} seq={seq} pm1={payload['pm1']} pm25={payload['pm25']} "
                f"pm10={payload['pm10']} temp={payload['temp_c']}C rh={payload['rh_pct']}% "
                f"gas={payload['gas_sensor']} alarm={payload['gas_alarm']} warmup={payload['warmup']} -> {res}"
            )
            seq += 1
            if count > 0 and seq >= count:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped live simulator.")


def main() -> int:
    parser = argparse.ArgumentParser(description="AirAura fake ESP32 sensor node simulator")
    parser.add_argument("--url", default="http://localhost:8000", help="Backend base URL")
    parser.add_argument("--key", default=_default_node_key(), help="X-Node-Key secret")
    parser.add_argument("--node", default="airaura-01", help="Node ID")
    parser.add_argument("--gas-sensor", default="MQ2", help="Gas sensor label")
    parser.add_argument("--interval", type=float, default=60.0, help="Live mode interval in seconds")
    parser.add_argument("--count", type=int, default=0, help="Live readings to send (0 = infinite)")
    parser.add_argument("--backfill", type=int, default=0, metavar="DAYS", help="Backfill N days @ 10m spacing")
    parser.add_argument("--admin-email", default=os.environ.get("ADMIN_EMAIL", "admin@ppcb.gov.in"))
    parser.add_argument("--admin-password", default=os.environ.get("ADMIN_PASSWORD", "admin@123"))
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    with requests.Session() as session:
        if args.backfill > 0:
            run_backfill(
                session=session,
                base_url=base_url,
                key=args.key,
                node_id=args.node,
                days=args.backfill,
                admin_email=args.admin_email,
                admin_password=args.admin_password,
                gas_sensor=args.gas_sensor,
            )
        else:
            run_live(
                session=session,
                base_url=base_url,
                key=args.key,
                node_id=args.node,
                interval=args.interval,
                count=args.count,
                gas_sensor=args.gas_sensor,
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
