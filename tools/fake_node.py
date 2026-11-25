"""Fake ESP32 AirAura node simulator for testing /api/ingest and aggregation.

Uses only Python stdlib + requests.
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
    seq: int,
    warmup: bool,
    rng: random.Random,
    fw: str = "0.1.0",
) -> dict:
    """Generate one realistic synthetic sensor reading matching §5 contract."""
    hour = ts.hour + ts.minute / 60.0

    # Bimodal diurnal PM2.5 curve (peaks ~08:30 and ~21:00), within 40-200 ug/m3.
    morning_peak = math.exp(-((hour - 8.5) ** 2) / (2 * 2.2 ** 2))
    evening_peak = math.exp(-((hour - 21.0) ** 2) / (2 * 2.6 ** 2))
    diurnal = 0.55 * morning_peak + 0.95 * evening_peak
    pm25 = _clamp(45.0 + 135.0 * diurnal + rng.uniform(-12.0, 15.0), 40.0, 200.0)
    pm10 = round(pm25 * rng.uniform(1.5, 1.9), 1)
    pm25 = round(pm25, 1)

    # Temperature 8-25 C (coolest ~05:00, warmest ~14:30-15:00).
    temp_wave = 0.5 * (1.0 - math.cos(2.0 * math.pi * (hour - 5.0) / 24.0))
    temp_c = round(_clamp(9.0 + 15.0 * temp_wave + rng.uniform(-0.8, 0.8), 8.0, 25.0), 1)

    # Relative humidity 40-95%, inversely correlated with temperature.
    rh_base = 92.0 - ((temp_c - 8.0) / 17.0) * 48.0
    rh_pct = round(_clamp(rh_base + rng.uniform(-4.0, 4.0), 40.0, 95.0), 1)

    # MQ-135 Rs/R0 0.8-2.5 rising with pollution.
    pollution_norm = (pm25 - 40.0) / 160.0
    mq135_rs_r0 = round(
        _clamp(0.85 + 1.55 * pollution_norm + rng.uniform(-0.08, 0.08), 0.8, 2.5),
        2,
    )
    mq135_mv = round(_clamp(900.0 + mq135_rs_r0 * 600.0 + rng.uniform(-25.0, 25.0), 500.0, 3200.0))

    return {
        "node_id": node_id,
        "ts": ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "seq": seq,
        "pm25": pm25,
        "pm10": pm10,
        "mq135_mv": mq135_mv,
        "mq135_rs_r0": mq135_rs_r0,
        "temp_c": temp_c,
        "rh_pct": rh_pct,
        "warmup": warmup,
        "fw": fw,
    }


def fetch_next_seq(session: requests.Session, base_url: str, node_id: str) -> int:
    try:
        resp = session.get(f"{base_url}/api/nodes/{node_id}/status", timeout=5)
        if resp.status_code == 200:
            latest = resp.json().get("latest")
            if latest and isinstance(latest.get("seq"), int):
                return latest["seq"] + 1
    except requests.RequestException:
        pass
    return 1


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
) -> None:
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    total = days * 24 * 6  # 10-minute intervals
    start_ts = now - timedelta(minutes=10 * total)
    seq = fetch_next_seq(session, base_url, node_id)
    rng = random.Random(f"{node_id}-backfill-{days}")

    inserted = 0
    duplicates = 0
    for i in range(total):
        ts = start_ts + timedelta(minutes=10 * i)
        payload = generate_reading(
            node_id=node_id,
            ts=ts,
            seq=seq + i,
            warmup=(i < 3),
            rng=rng,
        )
        res = post_reading(session, base_url, key, payload)
        if res.get("duplicate"):
            duplicates += 1
        else:
            inserted += 1

    print(
        f"Backfilled {total} readings ({days} days @ 10m) for {node_id}: "
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
        f"{base_url}/api/admin/aggregate",
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
) -> None:
    seq = fetch_next_seq(session, base_url, node_id)
    rng = random.Random()
    sent = 0
    print(f"Starting live simulator for {node_id} -> {base_url} (interval={interval}s, start_seq={seq})")
    try:
        while count <= 0 or sent < count:
            now = datetime.now(timezone.utc)
            payload = generate_reading(
                node_id=node_id,
                ts=now,
                seq=seq,
                warmup=(sent < 3),
                rng=rng,
            )
            res = post_reading(session, base_url, key, payload)
            print(
                f"[{sent + 1}] seq={seq} pm25={payload['pm25']} pm10={payload['pm10']} "
                f"rs_r0={payload['mq135_rs_r0']} temp={payload['temp_c']}C rh={payload['rh_pct']}% "
                f"warmup={payload['warmup']} -> {res}"
            )
            seq += 1
            sent += 1
            if count > 0 and sent >= count:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped live simulator.")


def main() -> int:
    parser = argparse.ArgumentParser(description="AirAura fake ESP32 sensor node simulator")
    parser.add_argument("--url", default="http://localhost:8000", help="Backend base URL")
    parser.add_argument("--key", default=_default_node_key(), help="X-Node-Key secret")
    parser.add_argument("--node", default="airaura-01", help="Node ID")
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
            )
        else:
            run_live(
                session=session,
                base_url=base_url,
                key=args.key,
                node_id=args.node,
                interval=args.interval,
                count=args.count,
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
