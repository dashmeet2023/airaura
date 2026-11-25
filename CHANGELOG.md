# Changelog

## 2026-11-26

### Task 1 — India CPCB AQI
- **Backend (`backend/aqi_data.py`, `backend/server.py`):**
  - Replaced US-EPA PM2.5 breakpoints with continuous India CPCB sub-index breakpoints for both **PM2.5** (`0–30`, `30–60`, `60–90`, `90–120`, `120–250`, `250–380` µg/m³) and **PM10** (`0–50`, `50–100`, `100–250`, `250–350`, `350–430`, `430–510` µg/m³) via `_subindex()`.
  - Added `aqi_cpcb(pm25, pm10)` returning `(aqi, dominant_pollutant)` as `max(sub_pm25, sub_pm10)` capped at `500`, and updated `aqi_from_pm25()` to use CPCB PM2.5 breakpoints.
  - Updated `category_for_aqi()` and `HEALTH_TIPS` to the 6 CPCB categories: **Good** (`0–50`, `#10B981`, `good`), **Satisfactory** (`51–100`, `#84CC16`, `satisfactory`), **Moderate** (`101–200`, `#F59E0B`, `moderate`), **Poor** (`201–300`, `#F97316`, `poor`), **Very Poor** (`301–400`, `#EF4444`, `very_poor`), and **Severe** (`401–500`, `#7F1D1D`, `severe`).
  - Updated `synth_reading()`, `forecast_7d()`, and `/api/overview` `buckets` to compute and aggregate all 6 CPCB categories and `dominant_pollutant`.
- **Frontend (`frontend/src/lib/aqi.js` and UI components/pages):**
  - Updated `categoryForAqi()` and `AQI_SCALE` to the 6 CPCB categories with matching Tailwind classes (`lime-*` for `Satisfactory`, etc.).
  - Updated labels, grids, filters, and advisories across `AQIBigCard.jsx`, `ForecastStrip.jsx`, `SearchStations.jsx`, `Landing.jsx`, `StudentExplore.jsx`, `PCBDashboard.jsx`, `PCBStations.jsx`, and `PCBAdvisories.jsx` (replacing US-EPA text, expanding scale grids to 6 columns, removing `.split(" ")[0]` label truncation, and supporting all 6 category buckets/severities).
- **Environment & Gitignore:**
  - Created `backend/.env` with local MongoDB, JWT, CORS, and node key settings; ensured `backend/venv/` and `backend/.env` are ignored in `.gitignore`.

### Task 2 — Enforce `"student"` Role on Registration
- **Backend (`backend/server.py`):**
  - Hardened `POST /api/auth/register` to always assign `role = "student"` regardless of any `role` field supplied by the client; `pcb_official` accounts are created only via startup seeding.

### Task 3 — Hardware Ingest API & Aggregation
- **Backend (`backend/ingest.py`, `backend/server.py`):**
  - Added `POST /api/ingest` with `IngestReadingIn` Pydantic range validation (`pm25`/`pm10` `0–2000`, `temp_c` `-20–60`, `rh_pct` `0–100`, optional UTC `ts`) and `X-Node-Key` SHA-256 hash verification (`401` on missing/wrong key).
  - Configured MongoDB collections and indexes: `readings_raw` (`(node_id, seq)` unique deduplication returning `200 {"duplicate": true}`, `(node_id, ts)` index, and 90-day TTL on `received_at`), `readings_hourly`, `readings_daily`, and `nodes` (updating `last_seen` on valid readings).
  - Seeded default node `airaura-01` (`thapar-campus`, `key_hash` from `NODE_API_KEY`, `mq135_r0: null`) on startup.
  - Added idempotent upsert aggregation into `readings_hourly` and `readings_daily` (means + `count`, excluding `warmup=true`), scheduled every 10 minutes via a background `asyncio` task and manually triggerable via `POST /api/admin/aggregate` (`pcb_official` only).
  - Added `GET /api/nodes/{node_id}/status` returning `last_seen`, `online` (`last_seen < 5 min`), `days_of_daily_data`, and `latest` reading.

### Task 4 — Fake Node Simulator
- **Tools (`tools/fake_node.py`, `tools/README.md`):**
  - Added standalone simulator (`requests` + stdlib) supporting live mode (configurable `--interval`, incremental `seq`, diurnal PM2.5/PM10/temp/RH/MQ-135 curves, `warmup=true` for first 3 readings) and `--backfill N` mode (10-minute historical spacing followed by admin login and `POST /api/admin/aggregate`).
  - Documented usage, CLI flags, and examples in `tools/README.md`.

