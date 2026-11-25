# AirAura — Pre-Integration Analysis

Hardware inputs: **PM2.5, PM10 (PMS5003/SDS011) · Gas (MQ-135) · Temperature, Humidity (DHT22)** on an ESP32.
This covers what we have, what doesn't fit together yet, and what to build when the node is ready. Put it in the repo root so Antigravity can read it as context.

Checked against: `aqi_pred_trackA.ipynb`, `models.zip` (10 pickles), the `AIRAURA-main` repo, and the mid-sem report.

---

## 1. How each sensor maps to the current software

| Sensor reading | ML model uses it? | Backend today | Dashboard today |
|---|---|---|---|
| PM2.5 | ✅ main input (61% of model gain) | synthetic | shown |
| PM10 | ✅ (17% gain + 12% via lag1) | synthetic (= PM2.5 × 1.4–1.9) | shown |
| Gas (MQ-135) | ❌ no equivalent column in training data | not modelled | ❌ shows **fake** NO₂, SO₂, O₃, CO₂ instead |
| Temperature | ❌ not in Kaggle `station_day.csv` | synthetic | shown |
| Humidity | ❌ not in Kaggle `station_day.csv` | synthetic | shown |

**In short:** the deployed model uses 2 of the 5 readings. Gas, temp and humidity only get displayed, and the gas tiles currently show pollutants the hardware can't measure.

---

## 2. ML model findings (verified by loading the pickles)

**2.1 Only one pickle can be deployed.** `aqi_track_a_xgb.pkl` (11 features, no `station_code`) is identical to the one in `backend/ml/model/`. The other 9 models and `scaler_track_a.pkl` all expect 12 features **including `station_code`**, so they can't run on AirAura nodes. That includes SVR, the "best" model in the report.

**2.2 The "nowcast" mostly re-learns the CPCB formula.** Same-day PM2.5 + PM10 carry ~76% of the model's gain. Kaggle's AQI label is *computed from* those same-day concentrations, so R² 0.925 measures how well it reproduces the formula, not how well it predicts. Steady-state check (Nov weekday, PM10 = 1.7 × PM2.5):

| PM2.5 | Model | CPCB PM-only formula |
|---|---|---|
| 20 | 61 | 34 |
| 45 | 86 | 77 |
| 75 | 151 | 149 |
| 110 | 273 | 266 |
| 180 | 343 | 346 |
| 300 | 494 | 415 |

The two agree in the middle. They split at the extremes: at low PM the gas pollutants in the training labels push the model's answer up. **What this means:** at runtime the model gives you about what the CPCB formula already gives you. The report should describe it honestly as *"a learned CPCB-AQI estimator from PM-only inputs"*.

**2.3 There's no forecast model.** The report (§2.2.3) and UI promise a **7-day forecast**. `forecast_7d()` is random drift on synthetic data, and no trained model predicts future AQI.

**2.4 Track A and Track C aren't a like-for-like comparison.** Track A was tested on 60,052 rows and Track C on 10,846 (only rows where all 12 pollutants exist), so they use different test sets. That's why Track C has lower RMSE but *also* lower R² (0.899 vs 0.925). The "RMSE 14 vs 26" gap shouldn't be presented as the cost of dropping gases unless both tracks are re-run on the same rows.

**2.5 Two small leakage points** (minor, but worth fixing before final numbers):
- The per-station 99.9% clip is computed on the full series, so it includes the test period.
- `interpolate(limit_direction="both")` can back-fill from future days.

**2.6 The model works on daily data, the node samples every minute.** The model needs **daily means** plus **8 days of history** (lag7 / roll7). A new node can't give an ML prediction for its first 8 days.

---

## 3. Hardware → data notes (things that affect integration)

**MQ-135**
- It gives **one combined reading**. It can't be turned into NO₂/SO₂/O₃/CO ppm. Report it as `Rs/R0` or a 0–100 "gas index" with a trend.
- It needs a 24–48 h burn-in on first use and a few minutes' warm-up every power-on. Drop readings taken during warm-up.
- Calibrate `R0` in clean outdoor air. The readings drift strongly with temperature and humidity, which is the main reason the DHT22 matters.
- Powered at 5 V, its analog output can exceed 3.3 V. Put a **voltage divider** before the ESP32 pin.
- Use an **ADC1 pin (GPIO32–39)**, because ADC2 stops working while Wi-Fi is on. Read with `analogReadMilliVolts()`.

**PMS5003 / SDS011**
- Optical sensors **over-read when humidity is above ~75%**. That's common in Punjab winter mornings and fog. Use DHT22 RH to apply a humidity correction, or at least flag those readings.
- PMS5003's PM10 is estimated, not measured directly, and tends to read low on coarse dust. Keep this in mind, since the model leans on PM10.
- Decide between PMS5003 and SDS011. The report lists both.

**DHT22**
- Fine at 1 sample/min. Outdoors it needs a ventilated radiation shield, or the temperature reads high in sun.

**Power:** PM sensor ~100 mA + MQ-135 heater ~150 mA + ESP32 Wi-Fi peaks. A 5 V / 2 A USB supply is enough.

---

## 4. Backend / dashboard gaps

1. **Wrong AQI scale.** `aqi_from_pm25()` and `frontend/src/lib/aqi.js` use **US-EPA** breakpoints and labels ("Unhealthy for Sensitive", "Hazardous"). The report claims CPCB throughout. Switch to CPCB sub-indices for PM2.5 and PM10 (24 h avg), take the max, and use the 6 CPCB categories.
2. **No ingest endpoint and no stored readings.** Everything comes from `synth_reading()`, and MongoDB only holds users and advisories.
3. **Security bug: anyone can register as a PCB official.** `POST /api/auth/register` accepts `role: "pcb_official"` from anyone. The frontend hardcodes `student`, but a direct API call bypasses it. Force `student` on the server.
4. `memory/test_credentials.md` is committed and seeded passwords are defaults. Fine for a demo, but not for a deployed node.
5. **Docs say Flask in the report, the code is FastAPI.** Pick one wording (it's FastAPI).

---

## 5. Integration contract (build this when hardware is ready)

**Node → backend:** `POST /api/ingest` with header `X-Node-Key: <per-node secret>`, every 60 s

```json
{
  "node_id": "airaura-01",
  "ts": "2026-11-26T10:15:00Z",
  "seq": 1234,
  "pm25": 84.2, "pm10": 141.0,
  "mq135_mv": 1630, "mq135_rs_r0": 1.42,
  "temp_c": 17.8, "rh_pct": 71.0,
  "warmup": false,
  "fw": "0.1.0"
}
```
- The firmware buffers unsent readings while offline. `seq` + `node_id` lets the backend de-duplicate retries.
- NTP sync for `ts`. If not synced yet, the server sets the timestamp.

**MongoDB**
- `readings_raw`: one document per POST, indexed on `(node_id, ts)`, TTL ~90 days
- `readings_hourly`: means, plus a `count` so gaps are visible
- `readings_daily`: means → **this is what feeds the ML model**
- `nodes`: `node_id`, name, lat/lng, `key_hash`, `mq135_r0`, `last_seen`

**API changes**
- `current_reading`: latest raw values + CPCB AQI computed from **rolling 24 h PM means**
- `predict`: build features from `readings_daily`. If fewer than 8 days exist, return `{"status": "warming_up", "days_available": n}` and let the card show progress.
- Keep `synth_reading()` as a fallback for stations without hardware, but **label it simulated** in the response.

**Dashboard changes**
- Replace the NO₂/SO₂/O₃/CO₂ tiles with **one MQ-135 gas index tile** plus temp and humidity
- Show a "high humidity — PM may read high" badge when RH > 75%
- Show a node status chip (last seen, warming up, offline)
- Hide or relabel the 7-day forecast until a real model exists

---

## 6. ML next steps (in order of value)

1. **Next-day forecast on Kaggle.** Same notebook, target = AQI shifted by −1 day per station. This turns the "prediction" into a real forecast and makes the UI's forecast claim true. Retrain without `station_code`, export, done.
2. **Add temp/humidity to training.** Join Kaggle `city_day`/`station_day` to historical daily weather per city (e.g. Open-Meteo's historical archive, run on Kaggle with internet on). Without this, the DHT22 data can't feed the model.
3. **Gas index.** It can't come from Kaggle. Collect your own node data for the field window, then train a small calibration/correction model locally (PM + RH + temp + MQ-135 → co-located CPCB value). This is the "calibration" objective in the report.
4. Fix the two leakage points (§2.5) and re-run Track A vs C on the **same rows** before final numbers.

---

## 7. Report corrections for end-sem

- Flask → FastAPI. "Cloud database" → MongoDB.
- §3.2 says MQ-135 measures "VOCs and NOx" while §1.4 says gases aren't measured. Settle on "MQ-135 provides a combined, uncalibrated gas index".
- §3.4(b) implies Track A uses temp/humidity. It doesn't (as §3.1 row 8 correctly says).
- Explain why **XGBoost is deployed, not SVR**: no `station_code` dependency and ~600× faster inference. Report the deploy model's own RMSE/R² (the notebook's cell 1 prints these).
- Remove the 7-day forecast claim, or build step 6.1.
- Clean-up: duplicate §2.1.3/§2.1.4, broken `[?]` citations, stray "``latex id=" text on pp. 4 and 17, and Table 2.1 row 5 ("Alam et al.") vs reference 5 (Zhang et al.).

---

## 8. Antigravity task list (paste as prompts, one at a time)

1. "Add CPCB AQI (PM2.5 + PM10 sub-index, 24 h rolling mean, 6 categories) to `backend/aqi_data.py` and `frontend/src/lib/aqi.js`, replacing US-EPA. Keep function names."
2. "Force `role='student'` in `/api/auth/register`; PCB accounts only via seed/admin."
3. "Add `POST /api/ingest` per §5 of AIRAURA_ANALYSIS.md, with `nodes`, `readings_raw`, `readings_hourly`, `readings_daily` collections and an hourly/daily aggregation job."
4. "Switch `current_reading`/`history_24h`/`predict` to real node data when a node exists for the station, with synthetic fallback marked `simulated: true`."
5. "Update PollutantGrid: remove NO₂/SO₂/O₃/CO₂, add MQ-135 gas index tile, RH>75% warning badge, node status chip."
6. "ESP32 Arduino sketch: PMS5003 on UART2, MQ-135 on GPIO34 via divider, DHT22 on GPIO4; 60 s cycle; JSON POST per §5; SPIFFS ring buffer + retry; NTP; MQ-135 warm-up flag."
