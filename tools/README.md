# AirAura Tools — Fake Node Simulator

`tools/fake_node.py` simulates an AirAura ESP32 sensor node posting readings to `POST /api/ingest` using only the Python standard library and `requests`.

## Prerequisites

Run from the project root using the backend virtual environment (or any Python environment with `requests` installed):

```powershell
backend\venv\Scripts\python.exe tools\fake_node.py --help
```

## Backfill Historical Data

Insert `N` days of past readings at 10-minute spacing (e.g., 10 days = 1,440 readings), then log in as the seeded `pcb_official` admin and trigger `POST /api/admin/aggregate` to populate `readings_hourly` and `readings_daily`:

```powershell
backend\venv\Scripts\python.exe tools\fake_node.py --backfill 10
```

## Live Mode

Stream readings continuously at a fixed interval (default `60` seconds; first 3 readings set `warmup=true`):

```powershell
backend\venv\Scripts\python.exe tools\fake_node.py
```

Use `--interval` (in seconds) and optional `--count` for quick test runs:

```powershell
backend\venv\Scripts\python.exe tools\fake_node.py --interval 5 --count 3
```

## Options

| Flag | Default | Description |
|---|---|---|
| `--url` | `http://localhost:8000` | Backend API base URL |
| `--key` | `NODE_API_KEY` from env / `backend/.env` | Secret sent in `X-Node-Key` header |
| `--node` | `airaura-01` | Target `node_id` |
| `--interval` | `60.0` | Seconds between live readings |
| `--count` | `0` (`0` = run until Ctrl+C) | Number of live readings to send |
| `--backfill` | `0` | Backfill `N` days at 10-minute intervals and trigger aggregation |
| `--admin-email` | `admin@ppcb.gov.in` | Admin email used by `--backfill` to trigger aggregation |
| `--admin-password` | `admin@123` | Admin password used by `--backfill` |
