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

### Task 5 — Real Node Data in Backend API
- **Backend (`backend/ingest.py`, `backend/server.py`, `backend/aqi_data.py`):**
  - Added `get_node_for_station()`, `get_nodes_by_station()`, `is_node_online()`, `node_current_reading()`, `resolve_station_current()`, `resolve_station_history_24h()`, and `resolve_station_daily()`.
  - Updated station endpoints (`/stations`, `/stations/search`, `/stations/{station_id}`, `/stations/{station_id}/history`, `/stations/{station_id}/predict`, `/overview`) to async Motor lookups: stations with online hardware nodes (`thapar-campus` → `airaura-01`) return live non-warmup telemetry (`gas_index`, `rh_warning`, `simulated: false`, `source: "airaura-node"`, `node_status`), 24h rolling CPCB AQI, hourly `readings_hourly` history, and `readings_daily` ML predictions (returning `200 {"status": "warming_up", "days_available": n, "days_needed": 8}` when `< 8` days exist), automatically falling back to synthetic data (`simulated: true`) when offline or without data.
  - Marked all synthetic responses with `simulated: true`, `source: "simulated"`, and added `"simulated": true` + `"note": "Placeholder until forecast model is trained"` to `/forecast`.

### Task 6 — Hardware-Matched Dashboard UI
- **Frontend (`PollutantGrid.jsx`, `AQIBigCard.jsx`, `MLPredictionCard.jsx`, `ForecastStrip.jsx`, `PCBDashboard.jsx`, `PCBStations.jsx`):**
  - Updated `PollutantGrid.jsx` to show `PM 2.5`, `PM 10`, `MQ-135 gas index` (`Rs/R0`, `uncalibrated`), `Temperature`, and `Humidity` for live node stations (removing fake `NO₂`/`SO₂`/`O₃`/`CO₂`), while tagging simulated stations as `simulated`.
  - Added node status chip (`Live sensor`, `Warming up`, `Offline`, or `Simulated data`) and yellow `High humidity — PM may read high` badge (`rh_warning`) on `AQIBigCard.jsx`.
  - Updated `MLPredictionCard.jsx` to render `Collecting data: n/8 days` with a progress bar on `warming_up` and updated the model note to reference daily PM2.5/PM10 sensor averages.
  - Added `Simulated forecast — model in development` badge to `ForecastStrip.jsx` and live/simulated sensor badges on `PCBDashboard.jsx` and `PCBStations.jsx`.
  - Added browser verification screenshots in `docs/screenshots/`.

### UI Review Fixes
- **Backend (`backend/ingest.py`, `backend/aqi_data.py`):**
  - Added `pm25_24h` and `pm10_24h` to `current_reading` payloads for both live hardware nodes (24h rolling mean) and simulated stations (current baseline).
  - Updated `resolve_station_history_24h()` and `history_24h()` to compute 24-hour rolling CPCB AQI for each hourly point (using available data when fewer than 24 hours exist) so the 24h trend aligns with the headline AQI.
- **Frontend (`AQIBigCard.jsx`, `PCBDashboard.jsx`, `StudentDashboard.jsx`, `LocationDetail.jsx`, `PollutantGrid.jsx`, `index.css`):**
  - Labeled the headline AQI as `"CPCB AQI · 24-h avg"`, displayed the `pm25_24h`/`pm10_24h` averages beneath the number, and added `"Latest reading"` tags on the PM2.5 and PM10 tiles.
  - Updated PCB Overview `Active Stations` KPI subtitle to dynamic `"X live sensor · Y simulated"` counts.
  - Updated trend chart title to `"24-hour AQI trend (rolling 24-h avg)"` in `StudentDashboard.jsx` and `LocationDetail.jsx`.
  - Added an `Active Advisories` banner above `AQIBigCard` on `StudentDashboard.jsx` filtering station-targeted and global advisories (sorted newest first, max 3, styled by CPCB severity).
  - Changed `PollutantGrid.jsx` temperature and humidity bars to neutral slate (`#94A3B8`) instead of the AQI danger scale, and added `scroll-padding-top` / `scroll-mt-20` for sticky header scroll clearance.
- **Simulator (`tools/fake_node.py`):**
  - Adjusted diurnal curves to Patiala local time (IST) with realistic winter temperatures (`≈7 °C` at night to `≈22 °C` mid-afternoon) and higher nighttime humidity (up to `95%`).



