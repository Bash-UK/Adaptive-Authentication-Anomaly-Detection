import json
import os
from typing import Dict, List

import psycopg


class PostgresStateStore:
    def __init__(self, dsn: str, schema: str = "anomaly_engine", vector_keep: int = 12000):
        self.dsn = dsn
        self.schema = schema
        self.vector_keep = max(500, int(vector_keep))
        self.enabled = True
        self._ensure_schema()

    def _connect(self):
        return psycopg.connect(self.dsn)

    def _ensure_schema(self):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema}")
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self.schema}.user_behavior_state (
                        user_id TEXT PRIMARY KEY,
                        state_json JSONB NOT NULL,
                        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self.schema}.global_feature_buffer (
                        id BIGSERIAL PRIMARY KEY,
                        feature_vector JSONB NOT NULL,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self.schema}.user_risk_events (
                        id BIGSERIAL PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        event_ts TIMESTAMP NOT NULL,
                        risk DOUBLE PRECISION NOT NULL,
                        confidence DOUBLE PRECISION NOT NULL,
                        model_meta JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS idx_user_risk_events_user_ts
                    ON {self.schema}.user_risk_events(user_id, event_ts DESC)
                    """
                )
            conn.commit()

    def load_user_states(self) -> Dict[str, dict]:
        out: Dict[str, dict] = {}
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT user_id, state_json FROM {self.schema}.user_behavior_state")
                for user_id, state_json in cur.fetchall():
                    out[str(user_id)] = dict(state_json)
        return out

    def save_user_state(self, user_id: str, state_dict: dict):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO {self.schema}.user_behavior_state (user_id, state_json, updated_at)
                    VALUES (%s, %s::jsonb, NOW())
                    ON CONFLICT (user_id)
                    DO UPDATE SET state_json = EXCLUDED.state_json, updated_at = NOW()
                    """,
                    (user_id, json.dumps(state_dict)),
                )
            conn.commit()

    def load_global_vectors(self, limit: int) -> List[List[float]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT feature_vector
                    FROM {self.schema}.global_feature_buffer
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cur.fetchall()
        # Return oldest -> newest so model history order is stable.
        return [list(map(float, row[0])) for row in reversed(rows)]

    def append_global_vector(self, feature_vector: List[float]):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO {self.schema}.global_feature_buffer (feature_vector)
                    VALUES (%s::jsonb)
                    """,
                    (json.dumps(feature_vector),),
                )
                cur.execute(
                    f"""
                    DELETE FROM {self.schema}.global_feature_buffer
                    WHERE id < (
                        SELECT COALESCE(MAX(id) - %s, 0)
                        FROM {self.schema}.global_feature_buffer
                    )
                    """,
                    (self.vector_keep,),
                )
            conn.commit()

    def append_user_risk_event(self, user_id: str, event_ts: str, risk: float, confidence: float, model_meta: dict):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO {self.schema}.user_risk_events (user_id, event_ts, risk, confidence, model_meta)
                    VALUES (%s, %s::timestamp, %s, %s, %s::jsonb)
                    """,
                    (user_id, event_ts, float(risk), float(confidence), json.dumps(model_meta)),
                )
                # Keep table bounded per user for UI history purposes.
                cur.execute(
                    f"""
                    DELETE FROM {self.schema}.user_risk_events
                    WHERE user_id = %s
                      AND id < (
                        SELECT COALESCE(MAX(id) - 2000, 0)
                        FROM {self.schema}.user_risk_events
                        WHERE user_id = %s
                      )
                    """,
                    (user_id, user_id),
                )
            conn.commit()

    def load_user_risk_history(self, user_id: str, limit: int = 60) -> List[dict]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT event_ts, risk, confidence, model_meta
                    FROM {self.schema}.user_risk_events
                    WHERE user_id = %s
                    ORDER BY event_ts DESC
                    LIMIT %s
                    """,
                    (user_id, int(limit)),
                )
                rows = cur.fetchall()
        out = [
            {
                "timestamp": row[0].isoformat(),
                "risk": float(row[1]),
                "confidence": float(row[2]),
                "modelMeta": dict(row[3]) if row[3] else {},
            }
            for row in reversed(rows)
        ]
        return out

    def load_known_users(self, limit: int = 200) -> List[str]:
        safe_limit = max(1, int(limit))
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT user_id FROM (
                        SELECT user_id, MAX(updated_at) AS seen_at
                        FROM {self.schema}.user_behavior_state
                        GROUP BY user_id
                        UNION ALL
                        SELECT user_id, MAX(event_ts) AS seen_at
                        FROM {self.schema}.user_risk_events
                        GROUP BY user_id
                    ) u
                    GROUP BY user_id
                    ORDER BY MAX(seen_at) DESC
                    LIMIT %s
                    """,
                    (safe_limit,),
                )
                rows = cur.fetchall()
        return [str(row[0]) for row in rows if row and row[0]]


def build_store_from_env():
    enabled = os.getenv("ANOMALY_PG_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        return None
    dsn = os.getenv("ANOMALY_DB_DSN", "postgresql://postgres:postgres@host.docker.internal:5432/postgres")
    schema = os.getenv("ANOMALY_DB_SCHEMA", "anomaly_engine")
    vector_keep = int(os.getenv("ANOMALY_PG_VECTOR_KEEP", "12000"))
    try:
        return PostgresStateStore(dsn=dsn, schema=schema, vector_keep=vector_keep)
    except Exception:
        return None
