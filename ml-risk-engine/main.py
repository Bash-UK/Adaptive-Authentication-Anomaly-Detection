import os
from datetime import datetime
from threading import Lock
from typing import List, Optional

from fastapi import FastAPI
from pydantic import BaseModel

from realtime_engine import RealtimeAnomalyEngine
from state_store import build_store_from_env

app = FastAPI()
store = build_store_from_env()
engine = RealtimeAnomalyEngine(store=store)
engine_lock = Lock()
APP_VERSION = os.getenv("APP_VERSION", "2.0.0")


class DetectRequest(BaseModel):
    userId: Optional[str] = "anonymous"
    loginStatus: Optional[str] = "Success"
    countryCode: Optional[str] = "USA"
    loginHour: Optional[int] = None
    timestamp: Optional[str] = None
    failedAttemptsLastHour: Optional[int] = 0
    countryChangeFlag: Optional[int] = 0
    newDeviceFlag: Optional[int] = 0
    ipAddress: Optional[str] = ""

    # Legacy compatibility fields.
    features: Optional[List[float]] = None
    loginHourNormalized: Optional[float] = None
    ipRiskScore: Optional[float] = None


def _parse_timestamp(ts: Optional[str]) -> datetime:
    if ts:
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            pass
    return datetime.utcnow()


def _legacy_to_raw(payload: dict) -> dict:
    if payload.get("features"):
        f = payload["features"]
        payload["loginHourNormalized"] = float(f[0]) if len(f) > 0 else payload.get("loginHourNormalized")
        payload["newDeviceFlag"] = int(round(float(f[1]))) if len(f) > 1 else payload.get("newDeviceFlag", 0)
        payload["countryChangeFlag"] = int(round(float(f[2]))) if len(f) > 2 else payload.get("countryChangeFlag", 0)
        payload["ipRiskScore"] = float(f[4]) if len(f) > 4 else payload.get("ipRiskScore")

    if payload.get("loginHour") is None:
        norm = payload.get("loginHourNormalized")
        payload["loginHour"] = int(round(float(norm) * 23.0)) if norm is not None else 12

    if not payload.get("ipAddress") and payload.get("ipRiskScore") is not None:
        guess = int(max(1, min(254, round(float(payload["ipRiskScore"]) * 255.0))))
        payload["ipAddress"] = f"192.168.0.{guess}"
    return payload


@app.get("/health")
def health():
    with engine_lock:
        user_count = len(engine.users)
        global_samples = len(engine.global_model.vectors)
    return {
        "status": "ok",
        "mode": "unsupervised_realtime_behavioral",
        "state": {
            "trackedUsers": user_count,
            "globalSamples": global_samples,
            "globalModelReady": global_samples >= engine.global_model.min_fit,
            "persistence": "postgres" if store is not None else "memory_only",
        },
    }


@app.post("/detect")
def detect(req: DetectRequest):
    payload = _legacy_to_raw(req.model_dump())
    ts = _parse_timestamp(payload.get("timestamp"))
    with engine_lock:
        result = engine.process_event(
            user_id=payload.get("userId", "anonymous"),
            timestamp=ts,
            login_status=payload.get("loginStatus", "Success"),
            country_code=payload.get("countryCode", "USA"),
            device_changed_flag=int(payload.get("newDeviceFlag", 0)),
            country_changed_flag=int(payload.get("countryChangeFlag", 0)),
            login_hour=int(payload.get("loginHour", 12)),
            failed_attempts=int(payload.get("failedAttemptsLastHour", 0)),
            ip_address=payload.get("ipAddress", ""),
        )

    return {
        "risk": result["risk"],
        "confidence": result["confidence"],
        "components": result["components"],
        "state": result["state"],
        "model": {
            "type": "unsupervised-realtime-user-baseline-plus-isolation-forest",
            "trainedOffline": False,
        },
    }


@app.get("/history/{user_id}")
def history(user_id: str, limit: int = 60):
    safe_limit = max(1, min(500, int(limit)))
    with engine_lock:
        items = engine.user_history(user_id, limit=safe_limit)
    return {"userId": user_id, "points": items}


@app.get("/users")
def users(limit: int = 200):
    safe_limit = max(1, min(1000, int(limit)))
    with engine_lock:
        items = engine.tracked_users(limit=safe_limit)
    return {"users": items}


@app.get("/version")
def version():
    return {
        "service": "ml-risk-engine",
        "version": APP_VERSION,
        "mode": "unsupervised_realtime_behavioral",
    }
