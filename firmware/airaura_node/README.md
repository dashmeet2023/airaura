# AirAura Node firmware v0.2.0

Built for the wiring in the current hardware code: **ESP32 + PMS5003 + DHT11 + MQ-2 module (digital DO)**.
It replaces the old "ESP32_FIRE_MONITOR" access-point sketch. The node now joins your WiFi and sends one reading per minute to the AirAura backend. It also keeps a small local status page.

## Wiring

| Sensor | Sensor pin | ESP32 pin | Note |
|---|---|---|---|
| PMS5003 | VCC | 5V (VIN) | Needs 5 V for the fan |
| | GND | GND | |
| | TX | GPIO16 (RX2) | 3.3 V logic, safe |
| | RX | GPIO17 (TX2) | |
| DHT11 | VCC | 3.3V | |
| | DATA | GPIO4 | 10k pull-up to 3.3V if your board has no built-in one |
| | GND | GND | |
| MQ-2 module | VCC | 5V | The heater needs 5 V |
| | GND | GND | |
| | DO | GPIO32 **via divider** | ⚠ If the module runs on 5 V, DO swings to ~5 V. ESP32 pins are 3.3 V max. Use 10k (DO→GPIO32) + 20k (GPIO32→GND). |
| | AO (optional) | GPIO34 or 35 via the same kind of divider | Gives a real analog gas value. Set `GAS_AO_PIN` in config.h. |

**Recommended:** also wire AO. The DO pin only says above/below the threshold you set with the module's screw. AO gives a value the dashboard can trend.

## Setup
1. Install the **ESP32 board package** (Espressif) and the libraries **"DHT sensor library"** and **"Adafruit Unified Sensor"**.
2. Copy `config.example.h` → `config.h` and fill in WiFi, `SERVER_URL`, `NODE_ID`, `NODE_KEY`.
   - Local test: `SERVER_URL` = `http://<your-PC-IP>:8000`. The PC and the ESP32 must be on the same WiFi. Run the backend with `--host 0.0.0.0` and allow port 8000 in Windows Firewall.
   - Online: `SERVER_URL` = your Render URL (https).
3. Board: **ESP32 Dev Module**, upload, then open Serial Monitor at 115200.

## What it sends (every 60 s)
Each value is the median of all samples taken in that minute.
```json
{"node_id":"airaura-01","boot_id":3051234567,"seq":12,"ts":"2026-11-26T09:15:00Z",
 "pm1":41.0,"pm25":63.0,"pm10":88.0,"pm_samples":58,
 "temp_c":18.0,"rh_pct":71.0,
 "gas_sensor":"MQ2","gas_alarm":false,"gas_alarm_frac":0.0,"gas_mv":null,
 "warmup":false,"rssi":-61,"fw":"0.2.0"}
```
- A sensor with no valid samples in the minute is sent as `null`. It's never sent as 0.
- `boot_id` is random on every boot. The server de-duplicates on `(node_id, boot_id, seq)`, so a reboot never makes real data look like duplicates.
- If an upload fails, the reading is stored in flash (max 500) and resent once the connection is back.

## Serial messages
- `[wifi] connected, node page: http://192.168.x.x`: open this IP in a browser on the same WiFi to see the local status page
- `[http] 401`: `NODE_KEY` doesn't match `NODE_API_KEY` on the backend
- `[http] 422`: the backend rejected the payload (check the backend log)
- `[http] failed -1`: the server isn't reachable (wrong IP, firewall, or backend not running)

## Accuracy notes
- **PMS5003** is the reliable sensor here. Readings inflate above ~75% humidity, and the dashboard flags this.
- **DHT11** is only ±2 °C / ±5% RH, with a 20–80% RH range. Swap to a DHT22 or BME280 for real accuracy (change `DHT_TYPE`).
- **MQ-2** detects smoke/LPG/combustible gas. It's not a general air-quality gas sensor. Treat it as a smoke alarm/indicator.
- Let the MQ-2 burn in for 24–48 h on first use. The first 3 minutes after every boot are sent with `warmup=true` and excluded from averages.
