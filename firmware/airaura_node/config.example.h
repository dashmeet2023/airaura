// Copy this file to config.h and fill in your WiFi, backend URL, and node key.
// config.h is git-ignored — never commit real WiFi passwords or node keys.
#pragma once

// ---------- WiFi (the node must reach the backend over this network) ----------
#define WIFI_SSID     "YOUR_WIFI_SSID"
#define WIFI_PASS     "YOUR_WIFI_PASSWORD"

// ---------- Backend ----------
// Local test: your PC's IP on the same WiFi, e.g. "http://10.33.242.229:8000"
// (run uvicorn with --host 0.0.0.0 and allow port 8000 in Windows Firewall).
// Online: your Render URL, e.g. "https://airaura-api.onrender.com"
#define SERVER_URL    "http://PC_IP_HERE:8000"
#define NODE_ID       "airaura-01"
#define NODE_KEY      "airaura-node-01-secret"   // must match NODE_API_KEY in backend/.env

// ---------- Hardware (matches the current wiring) ----------
#define DHT_PIN       4
#define DHT_TYPE      DHT11     // change to DHT22 if you swap the sensor
#define PMS_RX        16        // ESP32 RX  <- PMS5003 TX
#define PMS_TX        17        // ESP32 TX  -> PMS5003 RX
#define GAS_SENSOR    "MQ2"     // "MQ2" or "MQ135" — only used as a label
#define GAS_DO_PIN    32        // module digital output (threshold alarm)
#define GAS_ACTIVE_LOW true     // most LM393 modules pull DO LOW on alarm
#define GAS_AO_PIN    -1        // set to 34 or 35 if you wire AO through a divider; -1 = not wired
#define GAS_AO_DIVIDER 1.5f     // 10k (top) + 20k (bottom) divider -> multiply by 1.5

// ---------- Timing ----------
#define SEND_INTERVAL_MS   60000UL   // one reading per minute
#define WARMUP_MS          180000UL  // first 3 minutes flagged warmup=true

// ---------- Local status page ----------
#define ENABLE_LOCAL_PAGE  false     // set true to serve local status page at http://<node-ip>/
