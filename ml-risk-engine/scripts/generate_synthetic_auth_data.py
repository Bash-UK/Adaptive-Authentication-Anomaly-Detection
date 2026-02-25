import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List

import numpy as np
import pandas as pd


COUNTRIES = ["USA", "Canada", "Germany", "Japan", "India", "UK", "France", "Brazil", "Australia"]
DEVICES = ["Desktop", "Mobile", "Tablet"]


@dataclass
class UserProfile:
    user_id: int
    home_country: str
    secondary_country: str
    primary_device: str
    secondary_device: str
    base_hour: float
    hour_std: float
    base_behavior: float


def make_ip(rng: np.random.Generator, private_bias: float = 0.6) -> str:
    if rng.random() < private_bias:
        block = rng.choice(["10", "172", "192"])
        if block == "10":
            return f"10.{rng.integers(0,256)}.{rng.integers(0,256)}.{rng.integers(1,255)}"
        if block == "172":
            return f"172.{rng.integers(16,32)}.{rng.integers(0,256)}.{rng.integers(1,255)}"
        return f"192.168.{rng.integers(0,256)}.{rng.integers(1,255)}"
    return f"{rng.integers(11,223)}.{rng.integers(0,256)}.{rng.integers(0,256)}.{rng.integers(1,255)}"


def generate_profile(rng: np.random.Generator, user_id: int) -> UserProfile:
    home = rng.choice(COUNTRIES)
    secondary = rng.choice([c for c in COUNTRIES if c != home])
    primary_device = rng.choice(DEVICES, p=[0.50, 0.40, 0.10])
    secondary_device = rng.choice([d for d in DEVICES if d != primary_device])
    base_hour = float(rng.integers(7, 22))
    hour_std = float(rng.uniform(1.2, 3.5))
    base_behavior = float(rng.normal(82, 8))
    return UserProfile(
        user_id=user_id,
        home_country=home,
        secondary_country=secondary,
        primary_device=primary_device,
        secondary_device=secondary_device,
        base_hour=base_hour,
        hour_std=hour_std,
        base_behavior=base_behavior,
    )


def bounded_hour(hour: float) -> int:
    return int(max(0, min(23, round(hour))))


def normal_event(profile: UserProfile, ts: datetime, rng: np.random.Generator) -> dict:
    country = profile.home_country if rng.random() < 0.9 else profile.secondary_country
    device = profile.primary_device if rng.random() < 0.88 else profile.secondary_device
    login_status = "Success" if rng.random() < 0.97 else "Fail"
    failed_attempts = int(rng.poisson(0.25 if login_status == "Success" else 1.1))
    session_duration = float(max(0.05, rng.lognormal(mean=3.3, sigma=0.7)))
    behavioral = float(np.clip(rng.normal(profile.base_behavior, 6.5), 20, 99.9))

    return {
        "User ID": profile.user_id,
        "Timestamp": ts,
        "Login Status": login_status,
        "IP Address": make_ip(rng, private_bias=0.7),
        "Device Type": device,
        "Location": country,
        "Session Duration": session_duration,
        "Failed Attempts": failed_attempts,
        "Behavioral Score": behavioral,
        "Anomaly": 0,
    }


def anomaly_event(profile: UserProfile, ts: datetime, rng: np.random.Generator) -> dict:
    scenario = rng.choice(
        ["impossible_travel", "credential_stuffing", "data_exfiltration", "bot_session"],
        p=[0.30, 0.30, 0.25, 0.15],
    )
    event = normal_event(profile, ts, rng)
    event["Anomaly"] = 1

    if scenario == "impossible_travel":
        event["Location"] = rng.choice([c for c in COUNTRIES if c not in [profile.home_country, profile.secondary_country]])
        event["Device Type"] = rng.choice(DEVICES)
        event["Login Status"] = rng.choice(["Success", "Fail"], p=[0.6, 0.4])
        event["Failed Attempts"] = int(rng.integers(2, 8))
        event["Behavioral Score"] = float(np.clip(rng.normal(42, 12), 1, 80))
    elif scenario == "credential_stuffing":
        event["Login Status"] = "Fail"
        event["Failed Attempts"] = int(rng.integers(6, 18))
        event["Session Duration"] = float(np.clip(rng.lognormal(mean=1.5, sigma=0.6), 0.02, 12.0))
        event["Behavioral Score"] = float(np.clip(rng.normal(35, 10), 1, 70))
        event["IP Address"] = make_ip(rng, private_bias=0.1)
    elif scenario == "data_exfiltration":
        event["Login Status"] = "Success"
        event["Failed Attempts"] = int(rng.integers(0, 3))
        event["Session Duration"] = float(np.clip(rng.lognormal(mean=5.1, sigma=0.55), 120, 2200))
        event["Behavioral Score"] = float(np.clip(rng.normal(28, 9), 1, 65))
        event["Location"] = rng.choice([profile.home_country, profile.secondary_country], p=[0.4, 0.6])
    else:  # bot_session
        event["Login Status"] = rng.choice(["Success", "Fail"], p=[0.35, 0.65])
        event["Failed Attempts"] = int(rng.integers(3, 14))
        event["Session Duration"] = float(np.clip(rng.lognormal(mean=0.6, sigma=0.5), 0.02, 6.0))
        event["Behavioral Score"] = float(np.clip(rng.normal(22, 8), 1, 60))
        event["IP Address"] = make_ip(rng, private_bias=0.05)

    return event


def generate_dataset(
    users: int,
    days: int,
    avg_events_per_user_per_day: float,
    anomaly_rate: float,
    seed: int,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    profiles = [generate_profile(rng, uid) for uid in range(1, users + 1)]
    start = datetime(2023, 1, 1, 0, 0, 0)

    rows: List[dict] = []
    for profile in profiles:
        for d in range(days):
            day_start = start + timedelta(days=d)
            n_events = int(max(0, rng.poisson(avg_events_per_user_per_day)))
            for _ in range(n_events):
                hour = bounded_hour(rng.normal(profile.base_hour, profile.hour_std))
                minute = int(rng.integers(0, 60))
                second = int(rng.integers(0, 60))
                ts = day_start + timedelta(hours=hour, minutes=minute, seconds=second)
                if rng.random() < anomaly_rate:
                    rows.append(anomaly_event(profile, ts, rng))
                else:
                    rows.append(normal_event(profile, ts, rng))

    df = pd.DataFrame(rows)
    df = df.sort_values("Timestamp").reset_index(drop=True)
    df["Timestamp"] = df["Timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
    return df


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic auth anomaly dataset.")
    parser.add_argument("--users", type=int, default=1000)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--events-per-user-per-day", type=float, default=1.2)
    parser.add_argument("--anomaly-rate", type=float, default=0.12)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--output",
        type=str,
        default="data/synthetic_web_auth_logs_v2.csv",
    )
    args = parser.parse_args()

    df = generate_dataset(
        users=args.users,
        days=args.days,
        avg_events_per_user_per_day=args.events_per_user_per_day,
        anomaly_rate=args.anomaly_rate,
        seed=args.seed,
    )
    df.to_csv(args.output, index=False)

    print(f"Generated: {args.output}")
    print(f"Rows: {len(df)}")
    print("Anomaly ratio:", round(float(df['Anomaly'].mean()), 4))
    print("Login Status distribution:")
    print(df["Login Status"].value_counts(normalize=True).round(4).to_string())
    print("Top locations:")
    print(df["Location"].value_counts().head(8).to_string())


if __name__ == "__main__":
    main()
