"""Seed monitoring stations and synthetic time-series readings for AirAura."""
import math
import random
from datetime import datetime, timedelta, timezone

STATIONS = [
    {
        "id": "thapar-campus",
        "name": "Thapar Institute Campus",
        "city": "Patiala",
        "state": "Punjab",
        "lat": 30.3540,
        "lng": 76.3680,
        "type": "academic",
        "baseline_pm25": 58,
    },
    {
        "id": "patiala-city",
        "name": "Patiala City Center",
        "city": "Patiala",
        "state": "Punjab",
        "lat": 30.3398,
        "lng": 76.3869,
        "type": "urban",
        "baseline_pm25": 92,
    },
    {
        "id": "rajpura-industrial",
        "name": "Rajpura Industrial Estate",
        "city": "Rajpura",
        "state": "Punjab",
        "lat": 30.4836,
        "lng": 76.5945,
        "type": "industrial",
        "baseline_pm25": 145,
    },
    {
        "id": "ludhiana-civil",
        "name": "Ludhiana Civil Lines",
        "city": "Ludhiana",
        "state": "Punjab",
        "lat": 30.9010,
        "lng": 75.8573,
        "type": "urban",
        "baseline_pm25": 168,
    },
    {
        "id": "ludhiana-focal",
        "name": "Ludhiana Focal Point",
        "city": "Ludhiana",
        "state": "Punjab",
        "lat": 30.8650,
        "lng": 75.9020,
        "type": "industrial",
        "baseline_pm25": 212,
    },
    {
        "id": "amritsar-hall",
        "name": "Amritsar Hall Bazaar",
        "city": "Amritsar",
        "state": "Punjab",
        "lat": 31.6340,
        "lng": 74.8723,
        "type": "urban",
        "baseline_pm25": 124,
    },
    {
        "id": "jalandhar-junction",
        "name": "Jalandhar Junction",
        "city": "Jalandhar",
        "state": "Punjab",
        "lat": 31.3260,
        "lng": 75.5762,
        "type": "urban",
        "baseline_pm25": 108,
    },
    {
        "id": "bathinda-refinery",
        "name": "Bathinda Refinery Outskirts",
        "city": "Bathinda",
        "state": "Punjab",
        "lat": 30.2110,
        "lng": 74.9455,
        "type": "industrial",
        "baseline_pm25": 188,
    },
    {
        "id": "chandigarh-s17",
        "name": "Chandigarh Sector 17",
        "city": "Chandigarh",
        "state": "Chandigarh",
        "lat": 30.7416,
        "lng": 76.7836,
        "type": "urban",
        "baseline_pm25": 76,
    },
    {
        "id": "mohali-airport",
        "name": "Mohali Airport Road",
        "city": "Mohali",
        "state": "Punjab",
        "lat": 30.6951,
        "lng": 76.7250,
        "type": "residential",
        "baseline_pm25": 88,
    },
    {
        "id": "shimla-mall",
        "name": "Shimla Mall Road",
        "city": "Shimla",
        "state": "Himachal Pradesh",
        "lat": 31.1048,
        "lng": 77.1734,
        "type": "tourist",
        "baseline_pm25": 38,
    },
    {
        "id": "delhi-anandvihar",
        "name": "Delhi Anand Vihar",
        "city": "Delhi",
        "state": "Delhi",
        "lat": 28.6469,
        "lng": 77.3155,
        "type": "urban",
        "baseline_pm25": 235,
    },
]


_PM25_BREAKPOINTS = [
    (0.0, 30.0, 0, 50),
    (30.0, 60.0, 51, 100),
    (60.0, 90.0, 101, 200),
    (90.0, 120.0, 201, 300),
    (120.0, 250.0, 301, 400),
    (250.0, 380.0, 401, 500),
]

_PM10_BREAKPOINTS = [
    (0.0, 50.0, 0, 50),
    (50.0, 100.0, 51, 100),
    (100.0, 250.0, 101, 200),
    (250.0, 350.0, 201, 300),
    (350.0, 430.0, 301, 400),
    (430.0, 510.0, 401, 500),
]


def _subindex(concentration: float, breakpoints: list[tuple[float, float, int, int]]) -> int:
    """Piecewise-linear CPCB sub-index across continuous concentration breakpoints."""
    c = max(0.0, float(concentration))
    for c_low, c_high, a_low, a_high in breakpoints:
        if c <= c_high:
            val = ((a_high - a_low) / (c_high - c_low)) * (c - c_low) + a_low
            return min(500, round(val))
    return 500


def aqi_from_pm25(pm25: float) -> int:
    """India CPCB AQI sub-index calculation from PM2.5."""
    return _subindex(pm25, _PM25_BREAKPOINTS)


def aqi_cpcb(pm25: float, pm10: float | None = None) -> tuple[int, str]:
    """India CPCB AQI = max of PM2.5 and PM10 sub-indices (capped at 500) and dominant pollutant."""
    sub_pm25 = _subindex(pm25, _PM25_BREAKPOINTS)
    if pm10 is None:
        return min(500, sub_pm25), "PM2.5"
    sub_pm10 = _subindex(pm10, _PM10_BREAKPOINTS)
    if sub_pm25 >= sub_pm10:
        return min(500, sub_pm25), "PM2.5"
    return min(500, sub_pm10), "PM10"


def category_for_aqi(aqi: int) -> dict:
    if aqi <= 50:
        return {"label": "Good", "color": "#10B981", "code": "good"}
    if aqi <= 100:
        return {"label": "Satisfactory", "color": "#84CC16", "code": "satisfactory"}
    if aqi <= 200:
        return {"label": "Moderate", "color": "#F59E0B", "code": "moderate"}
    if aqi <= 300:
        return {"label": "Poor", "color": "#F97316", "code": "poor"}
    if aqi <= 400:
        return {"label": "Very Poor", "color": "#EF4444", "code": "very_poor"}
    return {"label": "Severe", "color": "#7F1D1D", "code": "severe"}


def _diurnal_factor(hour: int) -> float:
    """Pollution typically peaks early morning and evening rush hour."""
    return 1.0 + 0.25 * math.sin((hour - 6) / 12 * math.pi) + 0.12 * math.cos(hour / 6 * math.pi)


def synth_reading(station: dict, ts: datetime, seed_offset: int = 0) -> dict:
    rnd = random.Random(f"{station['id']}-{ts.isoformat()}-{seed_offset}")
    base = station["baseline_pm25"]
    diurnal = _diurnal_factor(ts.hour)
    noise = rnd.uniform(-0.18, 0.22)
    pm25 = max(4.0, base * diurnal * (1 + noise))
    pm10 = pm25 * rnd.uniform(1.4, 1.9)
    co2 = 380 + (pm25 / 200) * 600 + rnd.uniform(-30, 80)
    no2 = max(5, pm25 * rnd.uniform(0.18, 0.32))
    so2 = max(2, pm25 * rnd.uniform(0.05, 0.15))
    o3 = max(8, 30 + (24 - abs(ts.hour - 14)) * rnd.uniform(0.8, 1.8))
    temp = 18 + 9 * math.sin((ts.hour - 9) / 12 * math.pi) + rnd.uniform(-1.5, 1.5)
    humidity = max(20, min(95, 65 - (temp - 22) * 1.6 + rnd.uniform(-6, 6)))
    aqi, dominant = aqi_cpcb(pm25, pm10)
    return {
        "timestamp": ts.isoformat(),
        "pm25": round(pm25, 1),
        "pm10": round(pm10, 1),
        "co2": round(co2, 0),
        "no2": round(no2, 1),
        "so2": round(so2, 1),
        "o3": round(o3, 1),
        "temperature": round(temp, 1),
        "humidity": round(humidity, 1),
        "aqi": aqi,
        "dominant_pollutant": dominant,
        "category": category_for_aqi(aqi),
    }


def history_24h(station: dict, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    return [
        synth_reading(station, now - timedelta(hours=23 - i))
        for i in range(24)
    ]


def forecast_7d(station: dict, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    out = []
    # Linear drift trend + noise across upcoming days
    drift = random.Random(station["id"]).uniform(-0.06, 0.08)
    for i in range(1, 8):
        future = now + timedelta(days=i)
        scaled = dict(station)
        scaled["baseline_pm25"] = station["baseline_pm25"] * (1 + drift * i)
        # noon-ish forecast
        ts = future.replace(hour=12, minute=0, second=0, microsecond=0)
        r = synth_reading(scaled, ts, seed_offset=i)
        out.append({
            "date": future.date().isoformat(),
            "aqi": r["aqi"],
            "pm25": r["pm25"],
            "pm10": r["pm10"],
            "dominant_pollutant": r["dominant_pollutant"],
            "category": r["category"],
        })
    return out


def current_reading(station: dict) -> dict:
    return synth_reading(station, datetime.now(timezone.utc))


def daily_history(station: dict, days: int = 10, now: datetime | None = None) -> list[dict]:
    """One synthetic reading per day (noon), oldest first.

    Used to build the lag/rolling-window features the Track A ML model
    was trained on (PM2.5_lag7, PM10_roll7_mean, etc). Needs at least 8
    days for lag7/roll7 to be defined on the most recent day.
    """
    now = now or datetime.now(timezone.utc)
    out = []
    for i in range(days - 1, -1, -1):
        day = (now - timedelta(days=i)).replace(hour=12, minute=0, second=0, microsecond=0)
        out.append(synth_reading(station, day, seed_offset=500 + i))
    return out


HEALTH_TIPS = {
    "good": [
        "Air quality is excellent. Perfect day for outdoor activities and exercise.",
        "Open windows to let fresh air circulate indoors.",
    ],
    "satisfactory": [
        "Air quality is acceptable. Sensitive individuals should watch for minor breathing discomfort.",
        "Outdoor activities are generally safe; ventilate rooms during mid-day.",
    ],
    "moderate": [
        "People with asthma, lung or heart conditions, children and elderly should limit prolonged exertion.",
        "Consider a light walk; keep windows open during cleaner afternoon hours only.",
    ],
    "poor": [
        "Wear an N95 mask outdoors. Reduce prolonged outdoor exercise.",
        "Use air purifiers indoors. Avoid burning incense or candles.",
        "Children, elderly and sensitive groups should stay indoors during peak hours.",
    ],
    "very_poor": [
        "Avoid outdoor exercise. Wear an N95 mask if going outside is unavoidable.",
        "Keep windows closed and run air purifiers indoors continuously.",
        "Monitor respiratory symptoms closely and limit outdoor exposure.",
    ],
    "severe": [
        "Stay indoors. Air purifier ON. Wear N95 if you must go out.",
        "Avoid all outdoor exercise. Close all windows.",
        "Consult a doctor immediately if you have breathing difficulty.",
    ],
}


def health_tips_for(category_code: str) -> list[str]:
    return HEALTH_TIPS.get(category_code, HEALTH_TIPS["moderate"])
