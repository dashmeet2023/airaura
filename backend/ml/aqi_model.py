"""Track A AQI nowcast model integration.

Loads a pre-trained model (exported from aqi_pred_trackA.ipynb) and turns a
station's recent daily PM2.5/PM10 history into the same engineered features
the notebook trained on, then predicts AQI.

NOTE ON station_code: the notebook's original feature set included a
`station_code` column — a categorical code for one of the 110 nationwide
Kaggle training stations. AirAura's own 12 Punjab/Chandigarh stations were
never part of that training set, so passing a fabricated station_code would
be meaningless (and actively misleading, since XGBoost would treat it as a
real learned category). This module expects the exported model to have been
trained WITHOUT station_code, so it generalizes to any station from
pollutant + calendar features alone. See ml/README.md for the exact
notebook cell that trains and exports this version.
"""
import math
from pathlib import Path
from typing import Optional

import joblib

MODEL_PATH = Path(__file__).parent / "model" / "aqi_track_a_xgb.pkl"

# Order matters: must match the column order the model was trained on.
FEATURE_COLS = [
    "PM2.5", "PM10", "month_sin", "month_cos", "is_weekend",
    "PM2.5_lag1", "PM2.5_lag7", "PM2.5_roll7_mean",
    "PM10_lag1", "PM10_lag7", "PM10_roll7_mean",
]

_model = None
_load_error: Optional[str] = None
_attempted = False


def _load_model() -> None:
    global _model, _load_error, _attempted
    if _attempted:
        return
    _attempted = True
    try:
        _model = joblib.load(MODEL_PATH)
    except FileNotFoundError:
        _load_error = f"model file not found at {MODEL_PATH}"
    except Exception as e:  # bad pickle, version mismatch, etc.
        _load_error = str(e)


def model_status() -> dict:
    _load_model()
    return {"loaded": _model is not None, "error": _load_error, "path": str(MODEL_PATH)}


def _build_features(daily: list[dict], target_date) -> Optional[dict]:
    """daily: chronological (oldest -> newest) readings with 'pm25'/'pm10' keys,
    e.g. from aqi_data.daily_history(). Needs >= 8 days so lag7/roll7 are
    defined on the most recent day."""
    if len(daily) < 8:
        return None
    pm25 = [d["pm25"] for d in daily]
    pm10 = [d["pm10"] for d in daily]
    month = target_date.month
    dow = target_date.weekday()
    return {
        "PM2.5": pm25[-1],
        "PM10": pm10[-1],
        "month_sin": math.sin(2 * math.pi * month / 12),
        "month_cos": math.cos(2 * math.pi * month / 12),
        "is_weekend": 1 if dow >= 5 else 0,
        "PM2.5_lag1": pm25[-2],
        "PM2.5_lag7": pm25[-8],
        "PM2.5_roll7_mean": sum(pm25[-7:]) / 7,
        "PM10_lag1": pm10[-2],
        "PM10_lag7": pm10[-8],
        "PM10_roll7_mean": sum(pm10[-7:]) / 7,
    }


def predict_aqi(daily: list[dict], target_date=None) -> Optional[dict]:
    """Returns {"predicted_aqi": int, "features_used": {...}} or None if the
    model isn't loaded or there isn't enough history yet."""
    from datetime import datetime

    _load_model()
    if _model is None:
        return None
    target_date = target_date or datetime.now()
    feats = _build_features(daily, target_date)
    if feats is None:
        return None
    row = [[feats[c] for c in FEATURE_COLS]]
    pred = _model.predict(row)[0]
    return {"predicted_aqi": round(float(pred)), "features_used": feats}
