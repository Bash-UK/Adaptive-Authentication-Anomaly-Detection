from typing import Dict, Tuple

import pandas as pd


def parse_ip_last_octet(ip: str) -> int:
    try:
        parts = [int(x) for x in str(ip).split(".")]
        if len(parts) != 4 or any(x < 0 or x > 255 for x in parts):
            return 255
        return parts[3]
    except Exception:
        return 255


def _prepare_with_history(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    work["Timestamp"] = pd.to_datetime(work["Timestamp"], errors="coerce")
    work = work.sort_values(["User ID", "Timestamp"]).reset_index(drop=True)
    work["prev_location"] = work.groupby("User ID")["Location"].shift(1).fillna(work["Location"])
    work["prev_device"] = work.groupby("User ID")["Device Type"].shift(1).fillna(work["Device Type"])
    return work


def build_training_frame(csv_path: str) -> Tuple[pd.DataFrame, pd.Series]:
    df = pd.read_csv(csv_path)
    work = _prepare_with_history(df)

    features = pd.DataFrame(
        {
            "login_status": work["Login Status"].astype(str),
            "country_code": work["Location"].astype(str).str.upper(),
            "login_hour": work["Timestamp"].dt.hour.fillna(12).astype(int),
            "failed_attempts": work["Failed Attempts"].fillna(0).astype(int),
            "country_changed": (work["Location"] != work["prev_location"]).astype(int),
            "device_changed": (work["Device Type"] != work["prev_device"]).astype(int),
            "ip_last_octet": work["IP Address"].map(parse_ip_last_octet).astype(int),
        }
    )
    labels = work["Anomaly"].astype(int)
    return features, labels


def build_inference_row(payload: Dict) -> pd.DataFrame:
    login_hour = payload.get("loginHour")
    if login_hour is None:
        login_hour = round(float(payload.get("loginHourNormalized", 0.5)) * 23.0)

    ip_address = payload.get("ipAddress", "")
    if not ip_address and payload.get("ipRiskScore") is not None:
        # Legacy compatibility when only ipRiskScore is provided by caller.
        guess = int(max(0, min(255, round(float(payload["ipRiskScore"]) * 255.0))))
        ip_address = f"192.168.0.{guess}"

    row = {
        "login_status": str(payload.get("loginStatus", "Success")),
        "country_code": str(payload.get("countryCode", "US")).upper(),
        "login_hour": int(max(0, min(23, int(login_hour)))),
        "failed_attempts": int(max(0, int(payload.get("failedAttemptsLastHour", 0)))),
        "country_changed": int(payload.get("countryChangeFlag", 0)),
        "device_changed": int(payload.get("newDeviceFlag", 0)),
        "ip_last_octet": int(parse_ip_last_octet(ip_address)),
    }
    return pd.DataFrame([row])
