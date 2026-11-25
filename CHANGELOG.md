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

### Hardware Integration v0.2.0
- **Backend (`backend/ingest.py`, `backend/server.py`):**
  - Updated `IngestReadingIn` to the v0.2.0 ESP32 firmware payload (`boot_id`, nullable `pm1`/`pm25`/`pm10`/`temp_c`/`rh_pct`, `pm_samples`, `gas_sensor`, `gas_alarm`, `gas_alarm_frac`, nullable `gas_mv`, `rssi`, `fw`, plus optional legacy `mq135_*` fields).
  - Replaced `(node_id, seq)` dedup index with `(node_id, boot_id, seq)` (dropping legacy index on startup; missing `boot_id` defaults to `0`).
  - Added server timestamp correction (`ts_corrected=true` when `ts` is missing, >5 min in the future, or >7 days old).
  - Updated aggregation to compute null-ignoring means including `pm1`, `gas_alarm_frac`, and `gas_mv` in `"Asia/Kolkata"` timezone; periodic runs aggregate the last 48h while `POST /api/admin/aggregate?full=true` re-aggregates all history.
  - Updated `node_current_reading()` to fall back to the last non-null PM reading with `pm_stale=true`, expose `pm1`/`gas_sensor`/`gas_alarm`/`gas_alarm_frac`/`gas_mv`, and retain the last real reading (`node_status="offline"`, `stale=true`, `last_seen`) when offline (synthetic fallback only if a node never sent data).
  - Updated `/predict` to require >=12h hourly coverage per IST day (defaulting latest eligible day to yesterday when today isn't covered) and 8 consecutive covered days (returning `warming_up` with `reason="gap in data"` on gaps).
  - Hardened security: removed demo credential autofill from `Login.jsx`, deleted `memory/test_credentials.md`, added startup warnings and `ENV=production` admin-seed skip for missing/default passwords, and enforced trimmed CORS origin lists with `allow_credentials=False` when missing or `*`.
- **Frontend (`PollutantGrid.jsx`, `AQIBigCard.jsx`, `MLPredictionCard.jsx`, `useAutoRefresh.js`, pages):**
  - Replaced hardcoded MQ-135 gas tile with dynamic `Gas (<gas_sensor>)` showing red `"Smoke/gas detected"` / green `"Normal"` pills and optional `gas_mv`.
  - Added `PM 1` tile, `"PM sensor not responding"` (`pm_stale`) notes, and `"Offline since <time>"` greyed-out offline state.
  - Added visibility-aware 60s auto-refresh (`useAutoRefresh`) with `"Updated hh:mm:ss"` indicators across `StudentDashboard`, `LocationDetail`, `PCBDashboard`, `PCBStations`, and `PCBAdvisories`.
- **Firmware & Simulator (`firmware/airaura_node/`, `tools/fake_node.py`, `.gitignore`):**
  - Updated `tools/fake_node.py` to v0.2.0 payload (`boot_id`, `fw: "fake-0.2.0"`), set `SERVER_URL` (`http://10.33.242.229:8000`) in `firmware/airaura_node/config.h`, and added `firmware/airaura_node/config.h` to `.gitignore`.

### Firmware v0.2.1 Crash Fix
- **Firmware (`firmware/airaura_node/airaura_node.ino`, `firmware/airaura_node/config.example.h`):**
  - Fixed the v0.2.0 per-minute reboot caused by an lwIP `assert failed: pbuf_free` crash on stack-allocated `WiFiClient`/`WiFiClientSecure` instances during HTTP POST (not a USB power brownout).
  - Bumped `FW_VERSION` to `"0.2.1"`, moved `plainClient` and `secureClient` to globals, set `http.setReuse(false)`, `http.setConnectTimeout(5000)`, explicit `.stop()` after `http.end()`, `WiFi.setSleep(false)` in `setup()`, and defaulted `ENABLE_LOCAL_PAGE` to `false` in `config.example.h`.

### Advisory Delete & Expiry
- **Backend (`backend/server.py`):**
  - Added `DELETE /api/advisories/{advisory_id}` (`pcb_official` only, returning `404` when absent).
  - Added optional `expires_at` on `AdvisoryIn` / `POST /api/advisories`, normalizing timestamps to UTC ISO-8601 and defaulting to `created_at + 48h` when omitted or blank.
  - Updated `GET /api/advisories` to use optional authentication (`get_optional_user`) so students and unauthenticated callers only receive non-expired advisories (`expires_at > now`), while `pcb_official` retains full visibility (with optional `?active_only=true` filter).
  - Guarded startup sample advisory seeding behind `env != "production"` (including `expires_at` on dev samples) and removed the existing `"Improved Air Quality - Patiala"` sample advisory.
- **Frontend (`frontend/src/pages/PCBAdvisories.jsx`, `frontend/src/pages/StudentDashboard.jsx`):**
  - Added an inline two-step `Delete` -> `Confirm delete` / `Cancel` control on each advisory card in `PCBAdvisories.jsx`, an optional `Expires at (optional · default 48 h)` composer input, and `"Expired"` / expiry timestamp indicators on cards.
  - Added client-side expiry filtering in `StudentDashboard.jsx` so expired advisories are excluded from the active advisory banner.

### Production Deployment Config
- **Backend (`backend/requirements.txt`, `backend/requirements-dev.txt`, `backend/.python-version`, `backend/.env.example`, `backend/server.py`, `render.yaml`):**
  - Trimmed `backend/requirements.txt` to runtime-only dependencies, moved dev/tooling and simulator packages to `backend/requirements-dev.txt`, removed unused packages (`boto3`, `requests-oauthlib`, `python-jose`, `passlib`, `jq`, `typer`, `pandas`, `cryptography`, `python-multipart`, `tzdata`), and upgraded `motor` (`>=3.7.1,<4.0`) + `pymongo` (`>=4.9,<5.0`) for MongoDB 8 / Atlas compatibility.
  - Added `backend/.python-version` (`3.12`), `backend/.env.example`, root `render.yaml` (`airaura-api` free web service Blueprint), and `GET /api/health` (`{"status":"ok","db":"ok"|"error","model_loaded":bool}` with a 2 s DB ping timeout).
- **Frontend (`frontend/.npmrc`, `frontend/vercel.json`, `frontend/.env.example`):**
  - Added Vercel configuration (`legacy-peer-deps=true`, `CI=false npm run build`, `build` output directory, SPA rewrite to `/index.html`, and `REACT_APP_BACKEND_URL` example); verified `CI=true npm run build` passes cleanly with zero ESLint warnings.
- **Firmware & Docs (`firmware/airaura_node/config.example.h`, `firmware/airaura_node/airaura_node.ino`, `DEPLOYMENT.md`):**
  - Added commented Render HTTPS `SERVER_URL` example in `config.example.h` and raised timeouts over HTTPS (`setConnectTimeout(15000)`, `setTimeout(30000)`) in `airaura_node.ino` for Render cold starts.
  - Added step-by-step production deployment and key rotation guide in `DEPLOYMENT.md`.

### Final Pre-Push Hardening
- **Backend & Model (`backend/requirements.txt`, `backend/ml/model/aqi_track_a_xgb.json`, `backend/ml/aqi_model.py`, `render.yaml`):**
  - Pinned all 11 runtime packages in `backend/requirements.txt` to exact `pip freeze` versions from `backend/venv` without adding sub-dependencies.
  - Exported the XGBoost model to portable JSON (`backend/ml/model/aqi_track_a_xgb.json`) and updated `backend/ml/aqi_model.py` to load the `.json` model via `xgboost.Booster().load_model()` with `.pkl` fallback only when `.json` is missing (avoiding `scikit-learn` runtime dependency; verified 5 sample feature rows match within `< 0.01` with max diff `0.00000000`).
  - Pinned `PYTHON_VERSION=3.12.10` in `render.yaml` to match `backend/venv`.





