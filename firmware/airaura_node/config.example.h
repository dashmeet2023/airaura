// Copy this file to config.h (git-ignored) and set NODE_KEY.
// Wi-Fi is configured from a phone via the AirAura-Setup hotspot, not here.
#pragma once

// ---------- CONFIG ----------
// Wi-Fi is set from a phone via the "AirAura-Setup" hotspot (no Wi-Fi password in code)
#define SETUP_AP_NAME "AirAura-Setup"
#define SETUP_AP_PASS "airaura123"   // password of the setup hotspot (min 8 chars)
#define SETUP_BUTTON  0              // BOOT button: hold 5 s while running to reopen setup
#define SERVER_URL    "https://airaura-api.onrender.com"
#define NODE_ID       "airaura-01"
#define NODE_KEY      "PASTE_NODE_API_KEY_HERE"   // must equal NODE_API_KEY on Render

#define DHT_PIN       4
#define DHT_TYPE      DHT11
#define PMS_RX        16
#define PMS_TX        17
#define GAS_SENSOR    "MQ2"
#define GAS_DO_PIN    32
#define GAS_ACTIVE_LOW true
#define GAS_AO_PIN    -1
#define GAS_AO_DIVIDER 1.5f

#define SEND_INTERVAL_MS   60000UL
#define WARMUP_MS          180000UL
#define ENABLE_LOCAL_PAGE  false
