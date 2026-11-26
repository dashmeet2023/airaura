# AirAura Node firmware v0.3.0 (production)

Hardware: **ESP32 + PMS5003 + DHT11 + MQ-2 module (digital DO, optional analog AO)**.
The node joins Wi-Fi and sends one reading per minute to the deployed AirAura backend:
`https://airaura-api.onrender.com/api/ingest`

Wi-Fi is **not** written in the code. It is set from a phone through the node's own setup hotspot and saved on the board.

---

## 1. Wiring

| Sensor | Sensor pin | ESP32 pin | Note |
|---|---|---|---|
| PMS5003 | VCC | 5V (VIN) | Needs 5 V for the fan |
| | GND | GND | |
| | TX | GPIO16 (RX2) | 3.3 V logic, safe |
| | RX | GPIO17 (TX2) | |
| DHT11 | VCC | 3.3V | Keep **5–10 cm away from the MQ-2** (its heater makes the temperature read high) |
| | DATA | GPIO4 | 10k pull-up to 3.3V if the module has none |
| | GND | GND | |
| MQ-2 module | VCC | 5V | The heater needs 5 V |
| | GND | GND | |
| | DO | GPIO32 **via divider** | ⚠ At 5 V, DO swings to ~5 V. ESP32 pins are 3.3 V max: 10k (DO→GPIO32) + 20k (GPIO32→GND) |
| | AO (optional) | GPIO34 or 35 via the same kind of divider | Gives an analog gas value; set `GAS_AO_PIN` |
| BOOT button | — | GPIO0 (on-board) | Hold 5 s while running to reopen Wi-Fi setup |

## 2. One-time setup in Arduino IDE

1. Boards Manager → install **esp32 by Espressif Systems** (3.x). Board: **ESP32 Dev Module**.
2. Library Manager → install:
   - **DHT sensor library** (Adafruit)
   - **Adafruit Unified Sensor**
   - **WiFiManager** (by tzapu)
3. Copy `config.example.h` → `config.h` and set:
   - `SERVER_URL` = `"https://airaura-api.onrender.com"`
   - `NODE_KEY` = the value of `NODE_API_KEY` on Render (in `deploy_secrets.txt`). It must match exactly, or uploads fail with 401.
   - `config.h` is git-ignored. Never commit it.
4. Upload. If it hangs at "Connecting…", hold **BOOT** until writing starts.
5. Serial Monitor at **115200** baud.

## 3. Connecting the node to Wi-Fi (from a phone)

1. Power the node. If it has no saved Wi-Fi (or the saved one isn't in range), it opens a hotspot:
   - Name: **AirAura-Setup**
   - Password: **airaura123**
2. Connect your phone to it. The setup page opens automatically. If it doesn't, open **http://192.168.4.1**.
3. Tap **Configure WiFi** → choose the network → enter its password → **Save**.
4. The node restarts its connection and starts sending data. The Wi-Fi is remembered across power cuts.

**Wi-Fi requirements:** 2.4 GHz with internet access. 5 GHz-only networks are not supported. On a phone hotspot, enable 2.4 GHz / "Maximize Compatibility". Captive-portal networks (login pages) won't work.

**To change Wi-Fi later:** hold the **BOOT** button for **5 seconds** while the node is running, or power it on where the saved Wi-Fi isn't available. The AirAura-Setup hotspot opens again. If nobody configures it within 5 minutes, it restarts and tries the saved Wi-Fi again.

## 4. Daily use

Plug the node into any 5 V USB supply. It connects to the saved Wi-Fi, syncs time and sends a reading every 60 s. Open the dashboard at **https://airaura.vercel.app**. Thapar Institute Campus shows **Live sensor**.

## 5. What it sends (every 60 s)

Each value is the median of all samples taken in that minute (~57 PM frames, ~24 DHT reads, 60 gas checks).
```json
{"node_id":"airaura-01","boot_id":302800724,"seq":12,"ts":"2026-11-26T09:15:00Z",
 "pm1":41.0,"pm25":63.0,"pm10":88.0,"pm_samples":57,
 "temp_c":18.0,"rh_pct":71.0,
 "gas_sensor":"MQ2","gas_alarm":false,"gas_alarm_frac":0.00,"gas_mv":null,
 "warmup":false,"rssi":-61,"fw":"0.3.0"}
```
- A sensor with no valid samples is sent as `null`, never 0.
- The first 3 minutes after boot are flagged `warmup=true` and excluded from averages.
- `boot_id` is random per boot. The server de-duplicates on `(node_id, boot_id, seq)`.
- Failed uploads are stored in flash (max 500) and re-sent oldest-first when the connection returns.
- HTTPS uses long timeouts (15 s connect / 30 s response), because Render's free tier can take 30–60 s to wake.

## 6. Serial messages

| Message | Meaning / action |
|---|---|
| `join hotspot AirAura-Setup` | No saved Wi-Fi: set it up from a phone (section 3) |
| `[wifi] connected, node page: http://…` | Connected to Wi-Fi |
| `[time] NTP synced` | Internet works; readings get real timestamps |
| `[reading] {...}` with nothing after it | Upload succeeded |
| `[buffer] resent N, still queued 0` | Readings saved while offline were uploaded |
| `[http] 401` | `NODE_KEY` doesn't match Render's `NODE_API_KEY` |
| `[http] 422` | Backend rejected the payload (check Render logs) |
| `[http] failed -1 — buffering` | Server unreachable (no internet, or Render still waking); data is kept |
| `setup portal timed out, restarting` | Nobody configured Wi-Fi in 5 min; it retries |

## 7. Version history

| Version | Change |
|---|---|
| 0.3.0 | Production: Render HTTPS URL, Wi-Fi setup portal (WiFiManager), BOOT-hold to reconfigure, HTTPS timeouts |
| 0.2.1 | Fixed lwIP `assert failed: pbuf_free` crash (global HTTP clients, no reuse, socket closed after each POST, Wi-Fi sleep off) |
| 0.2.0 | New firmware for actual wiring: median per minute, null for missing sensors, boot_id dedup, LittleFS offline buffer, NTP |

## 8. Accuracy notes

- **PMS5003** is the reliable sensor here. Readings inflate above ~75 % RH, and the dashboard shows a warning.
- **DHT11** is ±2 °C / ±5 % RH. Swap to a DHT22 or BME280 for better accuracy (change `DHT_TYPE`).
- **MQ-2** detects smoke/LPG/combustible gas. It is a smoke indicator, not an air-quality gas sensor. Let it burn in for 24–48 h on first use.
- Absolute PM accuracy should be validated by co-locating the node with a CPCB reference station.
