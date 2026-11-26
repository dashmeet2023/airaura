# AirAura

**AirAura** is a low-cost, hyper-local air quality monitoring platform pairing an ESP32 sensor node with a live India **CPCB AQI** dashboard and ML prediction pipeline.

## Live Links

- **Live Dashboard:** https://airaura.vercel.app
- **API Health Check:** https://airaura-api.onrender.com/api/health

## Architecture

```text
ESP32 Sensor Node ──HTTPS POST──▶ Render (FastAPI + ML) ──▶ MongoDB Atlas
(PMS5003, DHT11, MQ-2)                                             ▲
                                         │                         │
                                    REST / JSON                    │
                                         ▼                         │
                                  Vercel (React SPA) ──────────────┘
```

**ESP32 → Render (FastAPI) → MongoDB Atlas → Vercel (React)**

## Hardware Used

- **Controller:** ESP32 Dev Module
- **Particulate Matter:** PMS5003 (PM1.0, PM2.5, PM10)
- **Temperature & Humidity:** DHT11
- **Gas / Smoke:** MQ-2 module (digital DO alarm, optional analog AO)

See **[firmware/airaura_node/README.md](firmware/airaura_node/README.md)** for full pinout and wiring details.

## How to Use

1. **Power the node** via USB (5 V).
2. **Connect Wi-Fi from your phone:**
   - Join the **`AirAura-Setup`** Wi-Fi hotspot (password: `airaura123`).
   - Use the captive portal to pick your Wi-Fi network and save credentials. *(Hold the ESP32 `BOOT` button for 5 seconds at any time to reopen `AirAura-Setup` and reconfigure Wi-Fi.)*
3. **Open the dashboard:** Visit https://airaura.vercel.app.
   - **Seeded accounts:** `admin@ppcb.gov.in` (PPCB portal) and `student@thapar.edu` (Student portal) — passwords are shared privately and **never** stored in this repository.
   - **Self-registration:** Any student can register their own account on the `/register` page.

## Important Notes

- **ML prediction (`xgboost_track_a_v1`):** Uses a same-day AQI nowcast; next-day forecasting is future work. Live node predictions start after **8 consecutive covered days** of real sensor data (`>=12` hours/day); before that, the card shows a collection progress indicator.
- **7-day forecast:** Currently simulated placeholder trends until multi-day forecast training data is accumulated.
- **Station simulation:** Only **Thapar Institute Campus (`thapar-campus`)** is backed by live hardware (`airaura-01`); all other stations are labeled **`Simulated`**.
- **Render free tier cold starts:** After 15 minutes of inactivity, Render may take **30–60 s** to wake on the first request (the ESP32 buffers failed readings in flash and flushes automatically).

## Repository Overview & Docs

- `backend/` — FastAPI backend, node ingest/aggregation (`ingest.py`), CPCB AQI calculator (`aqi_data.py`), and portable XGBoost JSON model (`ml/`)
- `frontend/` — React + Tailwind CSS dashboard configured for Vercel (`vercel.json`, `.npmrc`)
- `firmware/airaura_node/` — ESP32 Arduino sketch, `config.example.h`, and wiring README
- `tools/` — Local simulator (`fake_node.py`)
- `docs/` — UI screenshots and architecture artifacts
- **[DEPLOYMENT.md](DEPLOYMENT.md)** — Full MongoDB Atlas, Render, Vercel, ESP32 setup, and key-rotation guide
- **[CHANGELOG.md](CHANGELOG.md)** — Version-by-version project changelog
- **[AIRAURA_ANALYSIS.md](AIRAURA_ANALYSIS.md)** — Initial engineering & integration analysis

## Running Locally

```bash
# Backend (requires local MongoDB running on localhost:27017)
cd backend
python -m venv venv && venv\Scripts\activate   # or: source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                             # fill in local values
uvicorn server:app --host 0.0.0.0 --port 8000

# Frontend
cd frontend
npm install --legacy-peer-deps
npm start
```

> **Security:** Secrets are **never** committed (`backend/.env`, `frontend/.env`, and `firmware/airaura_node/config.h` are gitignored) — always configure from `.env.example` ([backend/.env.example](backend/.env.example), [frontend/.env.example](frontend/.env.example)) and [firmware/airaura_node/config.example.h](firmware/airaura_node/config.example.h).
