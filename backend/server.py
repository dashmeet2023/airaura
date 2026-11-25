from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import asyncio
import os
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List

import bcrypt
import jwt
from bson import ObjectId
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field, field_validator

from aqi_data import (
    STATIONS,
    daily_history,
    forecast_7d,
    health_tips_for,
    category_for_aqi,
)
from ml.aqi_model import predict_aqi, model_status
from ingest import (
    aggregation_loop,
    create_ingest_router,
    ensure_ingest_indexes,
    get_node_for_station,
    get_nodes_by_station,
    is_node_online,
    node_has_data,
    resolve_station_current,
    resolve_station_daily_for_predict,
    resolve_station_history_24h,
    seed_default_node,
)

# ---------- DB ----------
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# ---------- App ----------
app = FastAPI(title="AirAura API")
api = APIRouter(prefix="/api")
security = HTTPBearer(auto_error=False)

JWT_ALGORITHM = "HS256"


def jwt_secret() -> str:
    return os.environ["JWT_SECRET"]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(user_id: str, email: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=12),
        "type": "access",
    }
    return jwt.encode(payload, jwt_secret(), algorithm=JWT_ALGORITHM)


async def _resolve_user_from_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, jwt_secret(), algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    try:
        oid = ObjectId(payload["sub"])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await db.users.find_one({"_id": oid})
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    user["id"] = str(user["_id"])
    user.pop("_id", None)
    user.pop("password_hash", None)
    return user


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return await _resolve_user_from_token(credentials.credentials)


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[dict]:
    if credentials is None or not credentials.credentials:
        return None
    try:
        return await _resolve_user_from_token(credentials.credentials)
    except HTTPException:
        return None


def require_role(*roles: str):
    async def _checker(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return _checker


# ---------- Models ----------
class RegisterIn(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=6)
    role: Optional[str] = Field(default="student")  # ignored; server always assigns "student"
    home_station_id: Optional[str] = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


def _parse_utc_datetime(val: datetime | str) -> datetime:
    if isinstance(val, str):
        s = val.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
    elif isinstance(val, datetime):
        dt = val
    else:
        raise ValueError("Invalid datetime value")
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class AdvisoryIn(BaseModel):
    title: str
    message: str
    severity: str = Field(default="moderate")  # good | satisfactory | moderate | poor | very_poor | severe
    station_ids: List[str] = Field(default_factory=list)
    expires_at: Optional[datetime] = None

    @field_validator("expires_at", mode="before")
    @classmethod
    def _parse_expires_at(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return None
            return _parse_utc_datetime(s)
        if isinstance(v, datetime):
            return _parse_utc_datetime(v)
        raise ValueError("Invalid expires_at datetime")


# ---------- Auth Routes ----------
@api.post("/auth/register")
async def register(data: RegisterIn):
    email = data.email.lower().strip()
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    role = "student"  # PCB accounts are created only via startup seed/admin
    doc = {
        "name": data.name,
        "email": email,
        "password_hash": hash_password(data.password),
        "role": role,
        "home_station_id": data.home_station_id or "thapar-campus",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    res = await db.users.insert_one(doc)
    user_id = str(res.inserted_id)
    token = create_access_token(user_id, email, role)
    return {
        "token": token,
        "user": {
            "id": user_id,
            "name": data.name,
            "email": email,
            "role": role,
            "home_station_id": doc["home_station_id"],
        },
    }


@api.post("/auth/login")
async def login(data: LoginIn):
    email = data.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    user_id = str(user["_id"])
    token = create_access_token(user_id, email, user["role"])
    return {
        "token": token,
        "user": {
            "id": user_id,
            "name": user.get("name"),
            "email": email,
            "role": user["role"],
            "home_station_id": user.get("home_station_id", "thapar-campus"),
        },
    }


@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return {"user": user}


# ---------- Station / AQI Routes ----------
def _station_meta(s: dict, reading: dict, fields: tuple[str, ...]) -> dict:
    return {
        **{k: s[k] for k in fields},
        "simulated": reading["simulated"],
        "source": reading["source"],
        "node_status": reading.get("node_status"),
        "current": reading,
    }


@api.get("/stations")
async def list_stations():
    """Return all stations with current readings (live node or synthetic fallback)."""
    nodes_map = await get_nodes_by_station(db)
    readings = await asyncio.gather(*(
        resolve_station_current(db, s, nodes_map.get(s["id"]), _node_checked=True)
        for s in STATIONS
    ))
    fields = ("id", "name", "city", "state", "lat", "lng", "type")
    out = [_station_meta(s, r, fields) for s, r in zip(STATIONS, readings)]
    all_sim = all(item["simulated"] for item in out)
    return {
        "stations": out,
        "simulated": all_sim,
        "source": "simulated" if all_sim else "mixed",
    }


@api.get("/stations/search")
async def search_stations(q: str = ""):
    q = (q or "").lower().strip()
    if not q:
        return {"results": [], "simulated": True, "source": "simulated"}
    matches = [
        s for s in STATIONS
        if q in s["name"].lower() or q in s["city"].lower() or q in s["state"].lower()
    ][:10]
    nodes_map = await get_nodes_by_station(db)
    readings = await asyncio.gather(*(
        resolve_station_current(db, s, nodes_map.get(s["id"]), _node_checked=True)
        for s in matches
    ))
    fields = ("id", "name", "city", "state", "type")
    out = [_station_meta(s, r, fields) for s, r in zip(matches, readings)]
    all_sim = all(item["simulated"] for item in out) if out else True
    return {
        "results": out,
        "simulated": all_sim,
        "source": "simulated" if all_sim else "mixed",
    }


def _find_station(station_id: str) -> dict:
    for s in STATIONS:
        if s["id"] == station_id:
            return s
    raise HTTPException(status_code=404, detail="Station not found")


@api.get("/stations/{station_id}")
async def get_station(station_id: str):
    s = _find_station(station_id)
    reading = await resolve_station_current(db, s)
    return {
        "station": {k: s[k] for k in ("id", "name", "city", "state", "lat", "lng", "type")},
        "current": reading,
        "health_tips": health_tips_for(reading["category"]["code"]),
        "simulated": reading["simulated"],
        "source": reading["source"],
        "node_status": reading.get("node_status"),
    }


@api.get("/stations/{station_id}/history")
async def get_history(station_id: str):
    s = _find_station(station_id)
    history, simulated, source = await resolve_station_history_24h(db, s)
    return {"history": history, "simulated": simulated, "source": source}


@api.get("/stations/{station_id}/forecast")
async def get_forecast(station_id: str):
    s = _find_station(station_id)
    return {
        "forecast": forecast_7d(s),
        "simulated": True,
        "source": "simulated",
        "note": "Placeholder until forecast model is trained",
    }


@api.get("/stations/{station_id}/predict")
async def predict_station_aqi(station_id: str):
    """ML nowcast (Track A XGBoost model). Uses real readings_daily (>=12h/day,
    8 consecutive IST days) for nodes with data, or falls back to synthetic when
    no hardware data exists."""
    s = _find_station(station_id)
    node = await get_node_for_station(db, station_id)

    if node is not None and await node_has_data(db, node["node_id"]):
        pred_state = await resolve_station_daily_for_predict(db, node)
        if not pred_state["ready"]:
            payload = {
                "station_id": station_id,
                "status": "warming_up",
                "days_available": pred_state["days_available"],
                "days_needed": pred_state["days_needed"],
                "simulated": False,
                "source": "airaura-node",
            }
            if "reason" in pred_state:
                payload["reason"] = pred_state["reason"]
            return payload
        daily = pred_state["daily"]
        ld = pred_state["latest_date"]
        target_date = datetime(ld.year, ld.month, ld.day, tzinfo=timezone.utc)
        result = predict_aqi(daily, target_date=target_date)
        simulated = False
        source = "airaura-node"
        extra = {"node_status": "online" if is_node_online(node) else "offline"}
    else:
        daily = daily_history(s, days=10)
        result = predict_aqi(daily)
        simulated = True
        source = "simulated"
        extra = {}

    if result is None:
        status_info = model_status()
        detail = (
            "ML prediction model not deployed yet. Export it from the notebook "
            "and drop it at backend/ml/model/aqi_track_a_xgb.pkl (see backend/ml/README.md)."
            if not status_info["loaded"] else "Not enough station history to predict yet."
        )
        raise HTTPException(status_code=503, detail=detail)

    aqi = result["predicted_aqi"]
    feats = result["features_used"]
    return {
        "station_id": station_id,
        "status": "ok",
        "predicted_aqi": aqi,
        "category": category_for_aqi(aqi),
        "model": "xgboost_track_a_v1",
        "inputs": {"pm25": round(feats["PM2.5"], 1), "pm10": round(feats["PM10"], 1)},
        "based_on_days": len(daily),
        "simulated": simulated,
        "source": source,
        **extra,
    }


# ---------- PCB Overview ----------
@api.get("/overview")
async def overview(user: dict = Depends(require_role("pcb_official"))):
    nodes_map = await get_nodes_by_station(db)
    current_list = await asyncio.gather(*(
        resolve_station_current(db, s, nodes_map.get(s["id"]), _node_checked=True)
        for s in STATIONS
    ))
    readings = []
    buckets = {
        "good": 0,
        "satisfactory": 0,
        "moderate": 0,
        "poor": 0,
        "very_poor": 0,
        "severe": 0,
    }
    fields = ("id", "name", "city", "state", "lat", "lng", "type")
    for s, r in zip(STATIONS, current_list):
        buckets[r["category"]["code"]] += 1
        readings.append(_station_meta(s, r, fields))
    readings.sort(key=lambda x: x["current"]["aqi"], reverse=True)
    worst = readings[:3]
    best = sorted(readings, key=lambda x: x["current"]["aqi"])[:3]
    avg = round(sum(r["current"]["aqi"] for r in readings) / len(readings)) if readings else 0
    all_sim = all(item["simulated"] for item in readings)
    return {
        "summary": {
            "total_stations": len(readings),
            "average_aqi": avg,
            "average_category": category_for_aqi(avg),
            "buckets": buckets,
        },
        "hotspots": worst,
        "cleanest": best,
        "stations": readings,
        "simulated": all_sim,
        "source": "simulated" if all_sim else "mixed",
    }


def _is_advisory_active(doc: dict, now: datetime) -> bool:
    raw_exp = doc.get("expires_at")
    if raw_exp is None or raw_exp == "":
        return True
    try:
        return _parse_utc_datetime(raw_exp) > now
    except ValueError:
        return False


# ---------- Advisories ----------
@api.get("/advisories")
async def list_advisories(
    active_only: Optional[bool] = None,
    user: Optional[dict] = Depends(get_optional_user),
):
    docs = await db.advisories.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    is_pcb = user is not None and user.get("role") == "pcb_official"
    only_active = (not is_pcb) or bool(active_only)
    if only_active:
        now = datetime.now(timezone.utc)
        docs = [d for d in docs if _is_advisory_active(d, now)]
    return {"advisories": docs[:100]}


@api.post("/advisories")
async def create_advisory(
    data: AdvisoryIn,
    user: dict = Depends(require_role("pcb_official")),
):
    now = datetime.now(timezone.utc)
    exp_dt = data.expires_at if data.expires_at is not None else now + timedelta(hours=48)
    doc = {
        "id": str(uuid.uuid4()),
        "title": data.title,
        "message": data.message,
        "severity": data.severity,
        "station_ids": data.station_ids,
        "author_name": user.get("name"),
        "author_email": user.get("email"),
        "created_at": now.isoformat(),
        "expires_at": exp_dt.isoformat(),
    }
    await db.advisories.insert_one(doc)
    doc.pop("_id", None)
    return {"advisory": doc}


@api.delete("/advisories/{advisory_id}")
async def delete_advisory(
    advisory_id: str,
    user: dict = Depends(require_role("pcb_official")),
):
    res = await db.advisories.delete_one({"id": advisory_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Advisory not found")
    return {"deleted": True, "id": advisory_id}


@api.get("/")
async def root():
    return {"service": "AirAura API", "status": "ok"}


app.include_router(api)
app.include_router(create_ingest_router(db, require_role))

_raw_cors = os.environ.get("CORS_ORIGINS", "").strip()
_cors_origins = [o.strip() for o in _raw_cors.split(",") if o.strip()] if _raw_cors else ["*"]
_allow_credentials = bool(_raw_cors and "*" not in _cors_origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ---------- Startup ----------
@app.on_event("startup")
async def on_startup():
    await db.users.create_index("email", unique=True)
    await ensure_ingest_indexes(db)
    await seed_default_node(db)

    env = os.environ.get("ENV", "development").strip().lower()
    admin_password = os.environ.get("ADMIN_PASSWORD")
    student_password = os.environ.get("STUDENT_DEMO_PASSWORD")

    if not admin_password:
        logger.warning("ADMIN_PASSWORD is not set; using default demo password in non-production")
    if not student_password:
        logger.warning("STUDENT_DEMO_PASSWORD is not set; using default demo password in non-production")

    # Seed demo accounts
    seed_accounts = []
    if env == "production" and (not admin_password or admin_password == "admin@123"):
        logger.warning("ENV=production and ADMIN_PASSWORD is missing or default; skipping admin seed")
    else:
        seed_accounts.append({
            "email": os.environ.get("ADMIN_EMAIL", "admin@ppcb.gov.in"),
            "password": admin_password or "admin@123",
            "name": "PPCB Administrator",
            "role": "pcb_official",
            "home_station_id": "patiala-city",
        })

    if env == "production" and not student_password:
        logger.warning("ENV=production and STUDENT_DEMO_PASSWORD is missing; skipping student demo seed")
    else:
        seed_accounts.append({
            "email": os.environ.get("STUDENT_DEMO_EMAIL", "student@thapar.edu"),
            "password": student_password or "thapar@123",
            "name": "Thapar Student",
            "role": "student",
            "home_station_id": "thapar-campus",
        })
    for acc in seed_accounts:
        existing = await db.users.find_one({"email": acc["email"]})
        if existing is None:
            await db.users.insert_one({
                "email": acc["email"],
                "password_hash": hash_password(acc["password"]),
                "name": acc["name"],
                "role": acc["role"],
                "home_station_id": acc["home_station_id"],
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            logger.info("Seeded account: %s", acc["email"])
        elif not verify_password(acc["password"], existing["password_hash"]):
            await db.users.update_one(
                {"email": acc["email"]},
                {"$set": {"password_hash": hash_password(acc["password"])}},
            )
            logger.info("Updated password for: %s", acc["email"])

    # Seed sample advisories if empty (non-production only)
    if env != "production":
        count = await db.advisories.count_documents({})
        if count == 0:
            now = datetime.now(timezone.utc)
            samples = [
                {
                    "id": str(uuid.uuid4()),
                    "title": "Stubble Burning Alert - Ludhiana Belt",
                    "message": "Elevated PM2.5 levels detected across Ludhiana region due to paddy stubble burning. Residents advised to wear N95 masks outdoors.",
                    "severity": "severe",
                    "station_ids": ["ludhiana-civil", "ludhiana-focal"],
                    "author_name": "PPCB Administrator",
                    "author_email": "admin@ppcb.gov.in",
                    "created_at": now.isoformat(),
                    "expires_at": (now + timedelta(hours=48)).isoformat(),
                },
                {
                    "id": str(uuid.uuid4()),
                    "title": "Improved Air Quality - Patiala",
                    "message": "AQI levels in Patiala have improved to moderate range following overnight rainfall. Outdoor activities permissible with caution.",
                    "severity": "moderate",
                    "station_ids": ["patiala-city", "thapar-campus"],
                    "author_name": "PPCB Administrator",
                    "author_email": "admin@ppcb.gov.in",
                    "created_at": (now - timedelta(hours=6)).isoformat(),
                    "expires_at": (now + timedelta(hours=42)).isoformat(),
                },
            ]
            await db.advisories.insert_many(samples)
    else:
        logger.info("ENV=production; skipping sample advisory seed")

    app.state.aggregation_task = asyncio.create_task(aggregation_loop(db))


@app.on_event("shutdown")
async def on_shutdown():
    task = getattr(app.state, "aggregation_task", None)
    if task is not None:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    client.close()
