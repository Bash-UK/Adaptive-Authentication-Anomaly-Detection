import json
from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.compose import ColumnTransformer
from sklearn.metrics import average_precision_score, f1_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import OneHotEncoder, StandardScaler


COUNTRY_COORDS: Dict[str, Tuple[float, float]] = {
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

NUM_COLS = [
    "login_hour_sin",
    "login_hour_cos",
    "session_duration_log",
    "failed_attempts",
    "behavioral_risk",
    "is_fail",
    "country_changed",
    "device_changed",
    "time_gap_min_log",
    "failure_streak",
    "geo_jump_norm",
    "new_device_for_user",
    "new_country_for_user",
    "ip_is_private",
    "ip_last_octet_norm",
]

CAT_COLS = ["device_type", "country_code", "login_status"]


def parse_ip(ip: str) -> Tuple[bool, float]:
    try:
        parts = [int(x) for x in str(ip).split(".")]
        if len(parts) != 4 or any(x < 0 or x > 255 for x in parts):
            return False, 1.0
        is_private = (
            parts[0] == 10
            or (parts[0] == 172 and 16 <= parts[1] <= 31)
            or (parts[0] == 192 and parts[1] == 168)
            or parts[0] == 127
        )
        return is_private, parts[3] / 255.0
    except Exception:
        return False, 1.0


def to_rad(v: np.ndarray) -> np.ndarray:
    return v * (np.pi / 180.0)


def haversine_km(lat1: np.ndarray, lon1: np.ndarray, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    dlat = to_rad(lat2 - lat1)
    dlon = to_rad(lon2 - lon1)
    a = np.sin(dlat / 2.0) ** 2 + np.cos(to_rad(lat1)) * np.cos(to_rad(lat2)) * np.sin(dlon / 2.0) ** 2
    c = 2.0 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))
    return 6371.0 * c


def build_enhanced_frame(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
    df = df.sort_values(["User ID", "Timestamp"]).reset_index(drop=True)

    df["prev_timestamp"] = df.groupby("User ID")["Timestamp"].shift(1)
    df["prev_location"] = df.groupby("User ID")["Location"].shift(1).fillna(df["Location"])
    df["prev_device"] = df.groupby("User ID")["Device Type"].shift(1).fillna(df["Device Type"])

    # Streak of failed attempts per user, reset on success.
    failure_streak: List[int] = []
    streak = {}
    for uid, status in zip(df["User ID"], df["Login Status"]):
        uid = int(uid)
        if str(status).lower() == "fail":
            streak[uid] = streak.get(uid, 0) + 1
        else:
            streak[uid] = 0
        failure_streak.append(streak[uid])
    df["failure_streak"] = np.asarray(failure_streak, dtype=float)

    # First-seen device/country flags.
    seen_device: Dict[int, set] = {}
    seen_country: Dict[int, set] = {}
    new_device_for_user: List[float] = []
    new_country_for_user: List[float] = []
    for uid, dev, loc in zip(df["User ID"], df["Device Type"], df["Location"]):
        uid = int(uid)
        seen_device.setdefault(uid, set())
        seen_country.setdefault(uid, set())
        new_device_for_user.append(0.0 if dev in seen_device[uid] else 1.0)
        new_country_for_user.append(0.0 if loc in seen_country[uid] else 1.0)
        seen_device[uid].add(dev)
        seen_country[uid].add(loc)
    df["new_device_for_user"] = np.asarray(new_device_for_user, dtype=float)
    df["new_country_for_user"] = np.asarray(new_country_for_user, dtype=float)

    # Coordinates and geo jump.
    loc = df["Location"].astype(str).str.upper()
    prev_loc = df["prev_location"].astype(str).str.upper()
    lat = loc.map(lambda x: COUNTRY_COORDS.get(x, (np.nan, np.nan))[0]).to_numpy(dtype=float)
    lon = loc.map(lambda x: COUNTRY_COORDS.get(x, (np.nan, np.nan))[1]).to_numpy(dtype=float)
    prev_lat = prev_loc.map(lambda x: COUNTRY_COORDS.get(x, (np.nan, np.nan))[0]).to_numpy(dtype=float)
    prev_lon = prev_loc.map(lambda x: COUNTRY_COORDS.get(x, (np.nan, np.nan))[1]).to_numpy(dtype=float)
    geo = haversine_km(prev_lat, prev_lon, lat, lon)
    geo = np.nan_to_num(geo, nan=14000.0, posinf=14000.0, neginf=0.0)
    geo_jump_norm = np.clip(geo / 20015.0, 0.0, 1.0)

    # Time features.
    login_hour = df["Timestamp"].dt.hour.fillna(12).astype(float).to_numpy()
    login_hour_rad = 2.0 * np.pi * (login_hour / 24.0)
    time_gap = (df["Timestamp"] - df["prev_timestamp"]).dt.total_seconds().fillna(3600).to_numpy() / 60.0
    time_gap = np.clip(time_gap, 0.0, 60.0 * 24.0 * 7.0)

    ip_info = df["IP Address"].map(parse_ip)
    ip_is_private = np.asarray([1.0 if x[0] else 0.0 for x in ip_info], dtype=float)
    ip_last_octet_norm = np.asarray([x[1] for x in ip_info], dtype=float)

    out = pd.DataFrame(
        {
            "user_id": df["User ID"].astype(int),
            "timestamp": df["Timestamp"],
            "login_hour_sin": np.sin(login_hour_rad),
            "login_hour_cos": np.cos(login_hour_rad),
            "session_duration_log": np.log1p(df["Session Duration"].clip(lower=0.0).astype(float)),
            "failed_attempts": df["Failed Attempts"].fillna(0).astype(float),
            "behavioral_risk": np.clip(1.0 - (df["Behavioral Score"].fillna(50).astype(float) / 100.0), 0.0, 1.0),
            "is_fail": df["Login Status"].astype(str).str.lower().eq("fail").astype(float),
            "country_changed": (df["Location"] != df["prev_location"]).astype(float),
            "device_changed": (df["Device Type"] != df["prev_device"]).astype(float),
            "time_gap_min_log": np.log1p(time_gap),
            "failure_streak": df["failure_streak"].astype(float),
            "geo_jump_norm": geo_jump_norm,
            "new_device_for_user": df["new_device_for_user"].astype(float),
            "new_country_for_user": df["new_country_for_user"].astype(float),
            "ip_is_private": ip_is_private,
            "ip_last_octet_norm": ip_last_octet_norm,
            "device_type": df["Device Type"].astype(str),
            "country_code": loc,
            "login_status": df["Login Status"].astype(str),
            "label": df["Anomaly"].astype(int),
        }
    )
    return out


def make_preprocessor() -> ColumnTransformer:
    return ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), NUM_COLS),
            ("cat", OneHotEncoder(handle_unknown="ignore"), CAT_COLS),
        ]
    )


def transform_dense(pre: ColumnTransformer, x: pd.DataFrame) -> np.ndarray:
    arr = pre.transform(x[NUM_COLS + CAT_COLS])
    return arr.toarray().astype(np.float32) if hasattr(arr, "toarray") else np.asarray(arr, dtype=np.float32)


def build_sequences(df: pd.DataFrame, encoded: np.ndarray, seq_len: int, stride: int = 1) -> Tuple[np.ndarray, np.ndarray]:
    temp = df[["user_id", "timestamp", "label"]].copy()
    temp["row_idx"] = np.arange(len(temp))
    temp = temp.sort_values(["user_id", "timestamp"]).reset_index(drop=True)

    seq_x: List[np.ndarray] = []
    seq_y: List[int] = []
    for _, g in temp.groupby("user_id"):
        idx = g["row_idx"].to_numpy(dtype=int)
        labels = g["label"].to_numpy(dtype=int)
        if len(idx) < seq_len:
            continue
        for i in range(seq_len - 1, len(idx), stride):
            w = idx[i - seq_len + 1 : i + 1]
            seq_x.append(encoded[w])
            seq_y.append(int(labels[i]))
    if not seq_x:
        return np.empty((0, seq_len, encoded.shape[1]), dtype=np.float32), np.empty((0,), dtype=np.int64)
    return np.asarray(seq_x, dtype=np.float32), np.asarray(seq_y, dtype=np.int64)


class LSTMAutoEncoder(nn.Module):
    def __init__(self, input_dim: int, hidden: int = 64, latent: int = 32, dropout: float = 0.25):
        super().__init__()
        self.encoder = nn.LSTM(
            input_dim, hidden, num_layers=2, batch_first=True, dropout=dropout, bidirectional=True
        )
        self.project = nn.Sequential(
            nn.Linear(hidden * 2, latent),
            nn.LayerNorm(latent),
            nn.GELU(),
            nn.Dropout(dropout),
        )
        self.decoder = nn.LSTM(latent, hidden, num_layers=2, batch_first=True, dropout=dropout)
        self.output = nn.Linear(hidden, input_dim)

    def encode(self, x: torch.Tensor) -> torch.Tensor:
        e, _ = self.encoder(x)
        return self.project(e)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        z = self.encode(x)
        d, _ = self.decoder(z)
        return self.output(d)


def reconstruction_errors(model: nn.Module, x: np.ndarray, batch_size: int = 256) -> np.ndarray:
    errs: List[np.ndarray] = []
    model.eval()
    with torch.no_grad():
        for i in range(0, len(x), batch_size):
            batch = torch.tensor(x[i : i + batch_size], dtype=torch.float32)
            recon = model(batch)
            err = torch.mean(torch.abs(batch - recon), dim=(1, 2)).cpu().numpy()
            errs.append(err)
    return np.concatenate(errs) if errs else np.empty((0,), dtype=np.float32)


def latent_vectors(model: nn.Module, x: np.ndarray, batch_size: int = 256) -> np.ndarray:
    vecs: List[np.ndarray] = []
    model.eval()
    with torch.no_grad():
        for i in range(0, len(x), batch_size):
            batch = torch.tensor(x[i : i + batch_size], dtype=torch.float32)
            latent_seq = model.encode(batch)
            # Sequence embedding = mean latent state across window.
            latent = torch.mean(latent_seq, dim=1).cpu().numpy()
            vecs.append(latent)
    return np.concatenate(vecs) if vecs else np.empty((0, 1), dtype=np.float32)


def score_to_risk(train_scores: np.ndarray, target_scores: np.ndarray) -> np.ndarray:
    lo = float(np.percentile(train_scores, 5))
    hi = float(np.percentile(train_scores, 99))
    if hi <= lo:
        return np.full_like(target_scores, 0.5, dtype=float)
    return np.clip((target_scores - lo) / (hi - lo), 0.0, 1.0)


def best_threshold(y_true: np.ndarray, risk: np.ndarray) -> Tuple[float, float]:
    best_t, best_f1 = 0.5, -1.0
    for t in np.arange(0.05, 0.951, 0.01):
        pred = (risk >= t).astype(int)
        f1 = f1_score(y_true, pred, zero_division=0)
        if f1 > best_f1:
            best_f1 = float(f1)
            best_t = float(t)
    return best_t, best_f1


def evaluate(y_true: np.ndarray, risk: np.ndarray, threshold: float) -> Dict[str, float]:
    pred = (risk >= threshold).astype(int)
    return {
        "roc_auc": float(roc_auc_score(y_true, risk)),
        "pr_auc": float(average_precision_score(y_true, risk)),
        "f1": float(f1_score(y_true, pred, zero_division=0)),
        "threshold": float(threshold),
    }


def train_pipeline(
    dataset_path: str = "data/synthetic_web_auth_logs_v2.csv",
    seq_len: int = 10,
    seed: int = 42,
    stride: int = 3,
    max_epochs: int = 10,
) -> Dict[str, Dict[str, float]]:
    np.random.seed(seed)
    torch.manual_seed(seed)

    frame = build_enhanced_frame(dataset_path)
    users = frame["user_id"].unique()
    train_users, test_users = train_test_split(users, test_size=0.2, random_state=seed)
    fit_users, val_users = train_test_split(train_users, test_size=0.2, random_state=seed)

    fit_df = frame[frame["user_id"].isin(fit_users)].copy().reset_index(drop=True)
    val_df = frame[frame["user_id"].isin(val_users)].copy().reset_index(drop=True)
    test_df = frame[frame["user_id"].isin(test_users)].copy().reset_index(drop=True)

    pre = make_preprocessor()
    pre.fit(fit_df[NUM_COLS + CAT_COLS])

    x_fit = transform_dense(pre, fit_df)
    x_val = transform_dense(pre, val_df)
    x_test = transform_dense(pre, test_df)

    fit_seq_x, fit_seq_y = build_sequences(fit_df, x_fit, seq_len=seq_len, stride=stride)
    val_seq_x, val_seq_y = build_sequences(val_df, x_val, seq_len=seq_len, stride=stride)
    test_seq_x, test_seq_y = build_sequences(test_df, x_test, seq_len=seq_len, stride=stride)

    normal_fit = fit_seq_x[fit_seq_y == 0]
    normal_val = val_seq_x[val_seq_y == 0]

    if len(normal_fit) == 0 or len(test_seq_x) == 0:
        raise RuntimeError("Not enough sequence data for training/evaluation.")

    model = LSTMAutoEncoder(input_dim=fit_seq_x.shape[2], hidden=48, latent=24, dropout=0.2)
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.001, weight_decay=1e-4)
    loss_fn = nn.SmoothL1Loss()

    best_state = None
    best_val = float("inf")
    patience = 5
    patience_left = patience

    for _ in range(max_epochs):
        model.train()
        perm = torch.randperm(len(normal_fit))
        for i in range(0, len(normal_fit), 128):
            idx = perm[i : i + 128]
            batch = torch.tensor(normal_fit[idx], dtype=torch.float32)
            recon = model(batch)
            loss = loss_fn(recon, batch)
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()

        val_err = reconstruction_errors(model, normal_val if len(normal_val) else normal_fit[:256])
        mean_val = float(np.mean(val_err))
        if mean_val < best_val:
            best_val = mean_val
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
            patience_left = patience
        else:
            patience_left -= 1
            if patience_left <= 0:
                break

    if best_state is not None:
        model.load_state_dict(best_state)

    # AE standalone risk.
    fit_err = reconstruction_errors(model, normal_fit)
    val_err = reconstruction_errors(model, val_seq_x)
    test_err = reconstruction_errors(model, test_seq_x)
    val_ae_risk = score_to_risk(fit_err, val_err)
    test_ae_risk = score_to_risk(fit_err, test_err)

    ae_threshold, _ = best_threshold(val_seq_y, val_ae_risk)
    ae_metrics = evaluate(test_seq_y, test_ae_risk, ae_threshold)

    # LOF baseline on flattened sequence vectors.
    flat_normal = normal_fit.reshape(len(normal_fit), -1)
    flat_val = val_seq_x.reshape(len(val_seq_x), -1)
    flat_test = test_seq_x.reshape(len(test_seq_x), -1)
    lof_base = LocalOutlierFactor(
        n_neighbors=35,
        contamination=max(0.01, float(np.mean(fit_seq_y))),
        novelty=True,
    )
    lof_base.fit(flat_normal)
    train_lof_base = -lof_base.score_samples(flat_normal)
    val_lof_base = -lof_base.score_samples(flat_val)
    test_lof_base = -lof_base.score_samples(flat_test)
    val_lof_risk = score_to_risk(train_lof_base, val_lof_base)
    test_lof_risk = score_to_risk(train_lof_base, test_lof_base)
    lof_t, _ = best_threshold(val_seq_y, val_lof_risk)
    lof_metrics = evaluate(test_seq_y, test_lof_risk, lof_t)

    # Hybrid: AE reconstruction + LOF on latent embeddings.
    latent_fit = latent_vectors(model, normal_fit)
    latent_val = latent_vectors(model, val_seq_x)
    latent_test = latent_vectors(model, test_seq_x)
    latent_lof = LocalOutlierFactor(
        n_neighbors=25,
        contamination=max(0.01, float(np.mean(fit_seq_y))),
        novelty=True,
    )
    latent_lof.fit(latent_fit)
    lof_train = -latent_lof.score_samples(latent_fit)
    lof_val = -latent_lof.score_samples(latent_val)
    lof_test = -latent_lof.score_samples(latent_test)
    val_lof_latent_risk = score_to_risk(lof_train, lof_val)
    test_lof_latent_risk = score_to_risk(lof_train, lof_test)

    best_alpha = 0.5
    best_f1 = -1.0
    best_h_threshold = 0.5
    for alpha in np.arange(0.1, 1.0, 0.05):
        val_hybrid = alpha * val_ae_risk + (1.0 - alpha) * val_lof_latent_risk
        t, f1 = best_threshold(val_seq_y, val_hybrid)
        if f1 > best_f1:
            best_f1 = f1
            best_alpha = float(alpha)
            best_h_threshold = float(t)

    test_hybrid = best_alpha * test_ae_risk + (1.0 - best_alpha) * test_lof_latent_risk
    hybrid_metrics = evaluate(test_seq_y, test_hybrid, best_h_threshold)
    hybrid_metrics["alpha_ae"] = best_alpha

    output = {
        "dataset": dataset_path,
        "sequence_length": seq_len,
        "split_sizes": {
            "fit_sequences": int(len(fit_seq_x)),
            "val_sequences": int(len(val_seq_x)),
            "test_sequences": int(len(test_seq_x)),
            "test_anomaly_rate": float(np.mean(test_seq_y)),
        },
        "results": {
            "lof_baseline": lof_metrics,
            "lstm_autoencoder": ae_metrics,
            "lstm_autoencoder_plus_lof_latent": hybrid_metrics,
        },
    }
    return output


if __name__ == "__main__":
    result = train_pipeline()
    with open("lstm_sequence_benchmark.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result, indent=2))
