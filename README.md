# AirAura

Real-time air quality monitoring platform computing India **CPCB AQI** (PM2.5 & PM10), 24-hour rolling trends, XGBoost next-day AQI nowcasts, and targeted PPCB public health advisories.

## Architecture

```text
ESP32 Sensor Node ──HTTPS POST──▶ FastAPI on Render ──▶ MongoDB Atlas
  (PMS5003, DHT11, MQ-2)            (API + ML + Aggregator)        ▲
                                           │                       │
                                      REST / JSON                  │
                                           ▼                       │
                                    React on Vercel ───────────────┘
                              (Student & PPCB Portals)
```

- **ESP32 (`firmware/airaura_node/`):** Samples PMS5003 particulate matter (PM1/PM2.5/PM10), DHT11 temperature/humidity, and MQ-2 gas alarms every 60 seconds with LittleFS offline buffering and NTP timestamps.
- **Backend (`backend/`):** FastAPI API with `X-Node-Key` sensor ingestion, IST (`Asia/Kolkata`) hourly/daily aggregation, JWT role-based auth (`student` / `pcb_official`), advisory management with expiry, and XGBoost AQI prediction.
- **Database (MongoDB Atlas):** Stores raw telemetry (90-day TTL), aggregated hourly/daily buckets, nodes, users, and advisories.
- **Frontend (`frontend/`):** React + Tailwind CSS web app featuring live station monitoring, CPCB AQI scales, interactive charts, and PPCB advisory broadcasting.

## Repository Structure

```text
.
├── backend/                  # FastAPI server, ingest & aggregation, CPCB AQI logic
│   └── ml/                   # Portable XGBoost JSON model & inference wrapper
├── frontend/                 # React SPA (Vercel build & rewrite config)
├── firmware/airaura_node/    # ESP32 hardware firmware (v0.2.1) & config.example.h
├── tools/                    # fake_node.py simulator for testing & historical backfill
├── docs/                     # Reference documentation & UI screenshots
├── render.yaml               # Render Blueprint definition for airaura-api
├── DEPLOYMENT.md             # Step-by-step cloud & hardware deployment guide
└── CHANGELOG.md              # Project change history
```

## Deployment & Local Setup

Follow the step-by-step guide in **[DEPLOYMENT.md](DEPLOYMENT.md)** to deploy MongoDB Atlas, Render, Vercel, and flash your ESP32 node.

> **Security Note:** Real secrets are **never committed** to this repository (`backend/.env`, `frontend/.env`, and `firmware/airaura_node/config.h` are gitignored). Always copy the template files and supply your own generated keys and credentials:
> - [backend/.env.example](backend/.env.example) → `backend/.env`
> - [frontend/.env.example](frontend/.env.example) → `frontend/.env`
> - [firmware/airaura_node/config.example.h](firmware/airaura_node/config.example.h) → `firmware/airaura_node/config.h`
