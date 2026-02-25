from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Deque, Dict, Optional, Set, Tuple

import numpy as np
from sklearn.ensemble import IsolationForest


COUNTRY_COORDS = {
    "USA": (37.0902, -95.7129),
    "CANADA": (56.1304, -106.3468),
    "GERMANY": (51.1657, 10.4515),
    "JAPAN": (36.2048, 138.2529),
    "INDIA": (20.5937, 78.9629),
    "UK": (55.3781, -3.4360),
    "FRANCE": (46.2276, 2.2137),
    "BRAZIL": (-14.2350, -51.9253),
    "AUSTRALIA": (-25.2744, 133.7751),
}


def clamp01(v: float) -> float:
    return float(max(0.0, min(1.0, v)))


def parse_ip_risk(ip: str) -> float:
    try:
        parts = [int(x) for x in str(ip).split(".")]
        if len(parts) != 4 or any(x < 0 or x > 255 for x in parts):
            return 0.9
        is_private = (
            parts[0] == 10
            or (parts[0] == 172 and 16 <= parts[1] <= 31)
            or (parts[0] == 192 and parts[1] == 168)
            or parts[0] == 127
        )
        octet_risk = parts[3] / 255.0
        base = 0.25 + (0.5 * octet_risk)
        if is_private:
            base -= 0.2
        return clamp01(base)
    except Exception:
        return 0.9


def to_rad(v: float) -> float:
    return v * (np.pi / 180.0)


def haversine_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    dlat = to_rad(lat2 - lat1)
    dlon = to_rad(lon2 - lon1)
    q = np.sin(dlat / 2) ** 2 + np.cos(to_rad(lat1)) * np.cos(to_rad(lat2)) * np.sin(dlon / 2) ** 2
    c = 2 * np.arctan2(np.sqrt(q), np.sqrt(max(1e-9, 1 - q)))
    return float(6371.0 * c)


def robust_deviation(value: float, history: Deque[float], scale: float = 6.0) -> float:
    if len(history) < 8:
        return 0.0
    arr = np.asarray(history, dtype=float)
    med = float(np.median(arr))
    mad = float(np.median(np.abs(arr - med))) + 1e-6
    z = abs(value - med) / (1.4826 * mad)
    return clamp01(z / scale)


@dataclass
class UserState:
    count: int = 0
    last_ts: Optional[datetime] = None
    last_country: Optional[str] = None
    fail_streak: int = 0
    seen_countries: Set[str] = field(default_factory=set)
    seen_devices: Set[str] = field(default_factory=set)
    hour_hist: Deque[float] = field(default_factory=lambda: deque(maxlen=200))
    gap_hist: Deque[float] = field(default_factory=lambda: deque(maxlen=200))
    fail_hist: Deque[float] = field(default_factory=lambda: deque(maxlen=200))
    geo_hist: Deque[float] = field(default_factory=lambda: deque(maxlen=200))

    def to_dict(self) -> dict:
        return {
            "count": int(self.count),
            "last_ts": self.last_ts.isoformat() if self.last_ts else None,
            "last_country": self.last_country,
            "fail_streak": int(self.fail_streak),
            "seen_countries": sorted(list(self.seen_countries)),
            "seen_devices": sorted(list(self.seen_devices)),
            "hour_hist": list(self.hour_hist),
            "gap_hist": list(self.gap_hist),
            "fail_hist": list(self.fail_hist),
            "geo_hist": list(self.geo_hist),
        }

    @staticmethod
    def from_dict(raw: dict) -> "UserState":
        state = UserState()
        state.count = int(raw.get("count", 0))
        ts = raw.get("last_ts")
        state.last_ts = datetime.fromisoformat(ts) if ts else None
        state.last_country = raw.get("last_country")
        state.fail_streak = int(raw.get("fail_streak", 0))
        state.seen_countries = set(raw.get("seen_countries", []))
        state.seen_devices = set(raw.get("seen_devices", []))
        state.hour_hist.extend([float(x) for x in raw.get("hour_hist", [])][-200:])
        state.gap_hist.extend([float(x) for x in raw.get("gap_hist", [])][-200:])
        state.fail_hist.extend([float(x) for x in raw.get("fail_hist", [])][-200:])
        state.geo_hist.extend([float(x) for x in raw.get("geo_hist", [])][-200:])
        return state


class GlobalOutlierModel:
    def __init__(self, window_size: int = 12000, min_fit: int = 600, refit_every: int = 240):
        self.vectors: Deque[np.ndarray] = deque(maxlen=window_size)
        self.model: Optional[IsolationForest] = None
        self.min_fit = min_fit
        self.refit_every = refit_every
        self.events_since_refit = 0
        self.score_low = 0.0
        self.score_high = 1.0

    def add(self, vec: np.ndarray):
        self.vectors.append(vec)
        self.events_since_refit += 1
        if len(self.vectors) >= self.min_fit and (self.model is None or self.events_since_refit >= self.refit_every):
            self._refit()

    def _refit(self):
        x = np.stack(self.vectors, axis=0)
        self.model = IsolationForest(
            n_estimators=240,
            contamination=0.10,
            random_state=42,
        )
        self.model.fit(x)
        raw = -self.model.score_samples(x)
        self.score_low = float(np.percentile(raw, 5))
        self.score_high = float(np.percentile(raw, 95))
        if self.score_high <= self.score_low:
            self.score_high = self.score_low + 1e-6
        self.events_since_refit = 0

    def risk(self, vec: np.ndarray) -> float:
        if self.model is None:
            return 0.5
        raw = float(-self.model.score_samples(vec.reshape(1, -1))[0])
        return clamp01((raw - self.score_low) / (self.score_high - self.score_low))


class RealtimeAnomalyEngine:
    def __init__(self, store=None):
        self.users: Dict[str, UserState] = {}
        self.global_model = GlobalOutlierModel()
        self.store = store
        if self.store is not None:
            self._restore_from_store()

    def _restore_from_store(self):
        try:
            raw_states = self.store.load_user_states()
            self.users = {uid: UserState.from_dict(v) for uid, v in raw_states.items()}
            vectors = self.store.load_global_vectors(self.global_model.vectors.maxlen)
            for v in vectors:
                self.global_model.vectors.append(np.asarray(v, dtype=np.float32))
            if len(self.global_model.vectors) >= self.global_model.min_fit:
                self.global_model._refit()
        except Exception:
            # Continue in memory-only mode if persistence restore fails.
            self.store = None

    def process_event(
        self,
        user_id: str,
        timestamp: datetime,
        login_status: str,
        country_code: str,
        device_changed_flag: int,
        country_changed_flag: int,
        login_hour: int,
        failed_attempts: int,
        ip_address: str,
    ) -> Dict:
        uid = str(user_id or "anonymous")
        country = str(country_code or "USA").upper()
        status = str(login_status or "Success").lower()

        state = self.users.setdefault(uid, UserState())

        # Time gap
        gap_min = 60.0
        if state.last_ts is not None:
            gap_min = max(0.0, (timestamp - state.last_ts).total_seconds() / 60.0)
        gap_log = float(np.log1p(min(gap_min, 60.0 * 24.0 * 7.0)))

        # Geo jump
        geo_jump = 0.0
        if state.last_country and state.last_country in COUNTRY_COORDS and country in COUNTRY_COORDS:
            geo_jump = haversine_km(COUNTRY_COORDS[state.last_country], COUNTRY_COORDS[country])
        elif country_changed_flag == 1:
            geo_jump = 9000.0
        geo_jump_norm = clamp01(geo_jump / 20015.0)

        country_new = 1.0 if country not in state.seen_countries else 0.0
        device_new = 1.0 if device_changed_flag == 1 else 0.0

        hour = int(max(0, min(23, login_hour)))
        hour_arr = np.asarray(state.hour_hist, dtype=float)
        if len(hour_arr) >= 8:
            med_hour = float(np.median(hour_arr))
            circ_diff = min(abs(hour - med_hour), 24.0 - abs(hour - med_hour))
            hour_dev = clamp01(circ_diff / 8.0)
        else:
            hour_dev = 0.0

        fail_dev = robust_deviation(float(failed_attempts), state.fail_hist, scale=5.0)
        gap_dev = robust_deviation(gap_log, state.gap_hist, scale=6.0)
        geo_dev = robust_deviation(geo_jump_norm, state.geo_hist, scale=5.5)

        state.fail_streak = state.fail_streak + 1 if status == "fail" else 0
        streak_risk = clamp01(state.fail_streak / 6.0)
        status_risk = 0.35 if status == "fail" else 0.0

        novelty = 0.60 * country_new + 0.40 * device_new
        deviation = 0.25 * hour_dev + 0.25 * fail_dev + 0.20 * gap_dev + 0.20 * geo_dev + 0.10 * streak_risk
        cold_start = 0.20 * (1.0 - min(state.count / 12.0, 1.0))
        user_risk = clamp01((0.45 * novelty) + (0.40 * deviation) + status_risk + cold_start)

        ip_risk = parse_ip_risk(ip_address)
        hour_rad = 2.0 * np.pi * (hour / 24.0)
        global_vec = np.asarray(
            [
                np.sin(hour_rad),
                np.cos(hour_rad),
                clamp01(failed_attempts / 10.0),
                clamp01(gap_log / np.log1p(10080.0)),
                geo_jump_norm,
                country_new,
                device_new,
                1.0 if status == "fail" else 0.0,
                ip_risk,
                clamp01(streak_risk),
            ],
            dtype=np.float32,
        )

        self.global_model.add(global_vec)
        if self.store is not None:
            try:
                self.store.append_global_vector(global_vec.tolist())
            except Exception:
                pass
        global_risk = self.global_model.risk(global_vec)

        risk = clamp01((0.65 * user_risk) + (0.35 * global_risk))
        agreement = 1.0 - abs(user_risk - global_risk)
        confidence = clamp01(0.35 + (0.45 * min(state.count / 30.0, 1.0)) + (0.20 * agreement))

        # Update state after scoring to avoid data leakage in same event.
        state.count += 1
        state.last_ts = timestamp
        state.last_country = country
        state.seen_countries.add(country)
        state.hour_hist.append(float(hour))
        state.gap_hist.append(gap_log)
        state.fail_hist.append(float(failed_attempts))
        state.geo_hist.append(float(geo_jump_norm))

        if self.store is not None:
            try:
                self.store.save_user_state(uid, state.to_dict())
                self.store.append_user_risk_event(
                    uid,
                    timestamp.isoformat(),
                    risk,
                    confidence,
                    {
                        "userRisk": user_risk,
                        "globalOutlierRisk": global_risk,
                        "noveltyRisk": novelty,
                        "deviationRisk": deviation,
                    },
                )
            except Exception:
                pass

        return {
            "risk": risk,
            "confidence": confidence,
            "components": {
                "userRisk": user_risk,
                "globalOutlierRisk": global_risk,
                "noveltyRisk": novelty,
                "deviationRisk": deviation,
                "ipRiskHeuristic": ip_risk,
            },
            "state": {
                "userEventsSeen": state.count,
                "failStreak": state.fail_streak,
                "knownCountries": len(state.seen_countries),
            },
        }

    def user_history(self, user_id: str, limit: int = 60):
        if self.store is None:
            return []
        try:
            return self.store.load_user_risk_history(str(user_id), limit=limit)
        except Exception:
            return []

    def tracked_users(self, limit: int = 200):
        in_memory = list(self.users.keys())
        if self.store is None:
            return sorted(in_memory)[: max(1, int(limit))]
        try:
            from_store = self.store.load_known_users(limit=limit)
            merged = list(dict.fromkeys(from_store + in_memory))
            return merged[: max(1, int(limit))]
        except Exception:
            return sorted(in_memory)[: max(1, int(limit))]
