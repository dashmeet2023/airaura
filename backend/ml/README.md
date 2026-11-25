# ML AQI Prediction — Integration Notes

**Status: the real, Kaggle-trained model is deployed** (`model/aqi_track_a_xgb.pkl`),
not a placeholder. It's the XGBoost model from the notebook's export cell,
trained on ~60K real daily rows across 90 Indian monitoring stations
(2015–2020). `/api/stations/{id}/predict` is live and uses it.

This wires the Track A (sensor-only) nowcast model from `aqi_pred_trackA.ipynb`
into the AirAura dashboard as an independent "ML Model Prediction" card,
separate from the existing EPA-formula reading.

**The model's only pollutant inputs are PM2.5 and PM10** — no NO2, SO2, O3,
or CO2. Its full feature set is PM2.5, PM10, their 1-day/7-day lags, their
7-day rolling means, plus two calendar features (month seasonality, weekend
flag) derived from the date, not from any sensor. This was already true of
the feature engineering in Track A; it isn't a new constraint added for
AirAura.

**Predicted values run higher than the EPA-formula reading you'll see
elsewhere on the dashboard** — that's expected, not a bug. `aqi_from_pm25()`
in `aqi_data.py` uses US EPA PM2.5-only breakpoints; this model was trained
on India's CPCB-labeled AQI values and factors in PM10 too, both of which
push predictions up for the same underlying pollution level.

## Why the model had to change slightly

The notebook's `feature_cols_A` includes `station_code` — a categorical ID
for one of the 110 *nationwide* Kaggle stations it was trained on. AirAura's
12 Punjab/Chandigarh stations were never in that dataset, so there's no
correct `station_code` value to feed in for them at inference time.

The fix: retrain on the same features **minus `station_code`**, so the model
predicts AQI from pollutant + calendar signals alone (PM2.5, PM10, month
seasonality, weekend flag, lags, rolling means) — which generalizes to any
station. A new cell (cell 2) was added to the notebook that does this and
exports the result with `joblib.dump`.

## Re-deploying a newer model later

1. Run the notebook on Kaggle, then run the export cell at the end. It
   retrains an XGBoost model without `station_code` and saves
   `aqi_track_a_xgb.pkl` to the Kaggle output panel.
2. Download it and overwrite:
   ```
   backend/ml/model/aqi_track_a_xgb.pkl
   ```
3. Restart the backend. No other code changes needed — feature set and
   column order are identical.

## How the runtime features are built

`backend/aqi_data.py` has a new `daily_history(station, days=10)` function
that generates 10 days of synthetic daily PM2.5/PM10 (AirAura doesn't have
real sensors yet, so this reuses the same synthetic generator as the rest of
the app). `backend/ml/aqi_model.py` turns that into the exact feature set —
lag1/lag7, 7-day rolling mean, month sin/cos, weekend flag — the model
expects, **in the same column order it was trained on**. If you retrain with
a different feature set, update `FEATURE_COLS` in `aqi_model.py` to match.

## Swapping in a different model (e.g. SVR, Random Forest)

Your training run also produced 8 other models (`aqi_track_a_svr.pkl`,
`_random_forest.pkl`, `_gradient_boosting.pkl`, `_decision_tree.pkl`,
`_linear_regression.pkl`, `_ridge.pkl`, `_lasso.pkl`, `_knn.pkl`) plus
`scaler_track_a.pkl`. These aren't bundled here (Random Forest alone is
~170MB) but you already have them from your Kaggle run. Real results from
`model_comparison_results.csv`:

| Model | RMSE | R2 |
|---|---|---|
| SVR | 26.24 | 0.925 |
| Random Forest | 26.64 | 0.923 |
| **XGBoost (deployed)** | **27.74** | **0.916** |
| Gradient Boosting | 29.63 | 0.905 |
| Lasso / Ridge / Linear | ~32.5 | 0.885 |
| Decision Tree | 34.99 | 0.867 |
| KNN | 40.01 | 0.826 |

SVR and Random Forest score marginally better, but both were trained on
`feature_cols_A` **including `station_code`** — they won't work for
AirAura's stations without retraining without it (same fix as the XGBoost
deploy cell). SVR also predicts ~600x slower per sample than XGBoost. If you
want to swap one in, retrain it the same way the deploy cell does (drop
`station_code`, `joblib.dump`) and drop it in at the same path — no other
code changes needed as long as the feature order matches `FEATURE_COLS` in
`aqi_model.py`.
