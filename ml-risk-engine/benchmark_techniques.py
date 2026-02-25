import json
from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.compose import ColumnTransformer
from sklearn.mixture import BayesianGaussianMixture
from sklearn.model_selection import train_test_split
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, f1_score, roc_auc_score


NUM_COLS = ["login_hour", "failed_attempts", "country_changed", "device_changed", "ip_last_octet"]
CAT_COLS = ["login_status", "country_code"]


def parse_ip_last_octet(ip: str) -> int:
    try:
        parts = [int(x) for x in str(ip).split(".")]
        if len(parts) != 4 or any(x < 0 or x > 255 for x in parts):
            return 255
        return parts[3]
    except Exception:
        return 255


def load_frame(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
    df = df.sort_values(["User ID", "Timestamp"]).reset_index(drop=True)
    df["prev_location"] = df.groupby("User ID")["Location"].shift(1).fillna(df["Location"])
    df["prev_device"] = df.groupby("User ID")["Device Type"].shift(1).fillna(df["Device Type"])
    out = pd.DataFrame(
        {
            "user_id": df["User ID"].astype(int),
            "timestamp": df["Timestamp"],
            "login_status": df["Login Status"].astype(str),
            "country_code": df["Location"].astype(str).str.upper(),
            "login_hour": df["Timestamp"].dt.hour.fillna(12).astype(int),
            "failed_attempts": df["Failed Attempts"].fillna(0).astype(int),
            "country_changed": (df["Location"] != df["prev_location"]).astype(int),
            "device_changed": (df["Device Type"] != df["prev_device"]).astype(int),
            "ip_last_octet": df["IP Address"].map(parse_ip_last_octet).astype(int),
            "label": df["Anomaly"].astype(int),
        }
    )
    return out


def clamp01(x: np.ndarray) -> np.ndarray:
    return np.clip(x, 0.0, 1.0)


def normalize_scores(train_scores: np.ndarray, test_scores: np.ndarray) -> np.ndarray:
    low = float(np.percentile(train_scores, 5))
    high = float(np.percentile(train_scores, 95))
    if high <= low:
        return np.full_like(test_scores, 0.5, dtype=float)
    return clamp01((test_scores - low) / (high - low))


def metrics(y_true: np.ndarray, risk: np.ndarray) -> Dict[str, float]:
    best_t = 0.5
    best_f1 = -1.0
    for t in np.arange(0.10, 0.91, 0.01):
        f1 = f1_score(y_true, (risk >= t).astype(int))
        if f1 > best_f1:
            best_f1 = f1
            best_t = float(t)
    return {
        "roc_auc": float(roc_auc_score(y_true, risk)),
        "pr_auc": float(average_precision_score(y_true, risk)),
        "f1_best": float(best_f1),
        "best_threshold": best_t,
    }


def make_preprocessor() -> ColumnTransformer:
    return ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), NUM_COLS),
            ("cat", OneHotEncoder(handle_unknown="ignore"), CAT_COLS),
        ]
    )


@dataclass
class SeqData:
    x: np.ndarray
    y: np.ndarray


def build_sequences(df: pd.DataFrame, encoded: np.ndarray, seq_len: int = 6) -> SeqData:
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
        for i in range(seq_len - 1, len(idx)):
            window_idx = idx[i - seq_len + 1 : i + 1]
            seq_x.append(encoded[window_idx])
            seq_y.append(int(labels[i]))
    if not seq_x:
        return SeqData(np.empty((0, seq_len, encoded.shape[1]), dtype=np.float32), np.empty((0,), dtype=np.int64))
    return SeqData(np.stack(seq_x).astype(np.float32), np.asarray(seq_y, dtype=np.int64))


class LSTMAutoEncoder(nn.Module):
    def __init__(self, input_dim: int, hidden: int = 32):
        super().__init__()
        self.encoder = nn.LSTM(input_dim, hidden, batch_first=True)
        self.decoder = nn.LSTM(hidden, hidden, batch_first=True)
        self.output = nn.Linear(hidden, input_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        enc_out, (h, _) = self.encoder(x)
        # Repeat last latent state across sequence length for reconstruction.
        repeated = h[-1].unsqueeze(1).repeat(1, x.size(1), 1)
        dec_out, _ = self.decoder(repeated)
        return self.output(dec_out)


def benchmark(path: str) -> Dict[str, Dict[str, float]]:
    df = load_frame(path)
    idx = np.arange(len(df))
    y = df["label"].to_numpy()
    train_idx, test_idx = train_test_split(idx, test_size=0.2, random_state=42, stratify=y)

    train_df = df.iloc[train_idx].reset_index(drop=True)
    test_df = df.iloc[test_idx].reset_index(drop=True)

    pre = make_preprocessor()
    x_train_raw = pre.fit_transform(train_df[NUM_COLS + CAT_COLS])
    x_test_raw = pre.transform(test_df[NUM_COLS + CAT_COLS])
    x_train = x_train_raw.toarray().astype(np.float32) if hasattr(x_train_raw, "toarray") else np.asarray(x_train_raw, dtype=np.float32)
    x_test = x_test_raw.toarray().astype(np.float32) if hasattr(x_test_raw, "toarray") else np.asarray(x_test_raw, dtype=np.float32)

    y_train = train_df["label"].to_numpy()
    y_test = test_df["label"].to_numpy()
    normal_mask = y_train == 0

    results: Dict[str, Dict[str, float]] = {}

    # Isolation Forest
    iso = IsolationForest(contamination=max(0.01, float(y_train.mean())), n_estimators=300, random_state=42)
    iso.fit(x_train[normal_mask])
    iso_train_scores = -iso.score_samples(x_train[normal_mask])
    iso_test_scores = -iso.score_samples(x_test)
    iso_risk = normalize_scores(iso_train_scores, iso_test_scores)
    results["IsolationForest"] = metrics(y_test, iso_risk)

    # Local Outlier Factor
    lof = LocalOutlierFactor(n_neighbors=35, contamination=max(0.01, float(y_train.mean())), novelty=True)
    lof.fit(x_train[normal_mask])
    lof_train_scores = -lof.score_samples(x_train[normal_mask])
    lof_test_scores = -lof.score_samples(x_test)
    lof_risk = normalize_scores(lof_train_scores, lof_test_scores)
    results["LocalOutlierFactor"] = metrics(y_test, lof_risk)

    # Categorical Mixture Model approximation (mixture over one-hot + numeric transformed space).
    cmm = BayesianGaussianMixture(
        n_components=10,
        covariance_type="full",
        weight_concentration_prior_type="dirichlet_process",
        random_state=42,
        max_iter=500,
    )
    cmm.fit(x_train[normal_mask])
    cmm_train_scores = -cmm.score_samples(x_train[normal_mask])
    cmm_test_scores = -cmm.score_samples(x_test)
    cmm_risk = normalize_scores(cmm_train_scores, cmm_test_scores)
    results["CategoricalMixture"] = metrics(y_test, cmm_risk)

    # LSTM Autoencoder sequence anomaly detection.
    train_seq = build_sequences(train_df, x_train, seq_len=6)
    test_seq = build_sequences(test_df, x_test, seq_len=6)

    # Train only on normal sequences.
    normal_seq_mask = train_seq.y == 0
    x_train_seq = train_seq.x[normal_seq_mask]
    if len(x_train_seq) > 0 and len(test_seq.x) > 0:
        model = LSTMAutoEncoder(input_dim=x_train.shape[1], hidden=32)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
        loss_fn = nn.MSELoss()
        model.train()

        x_train_tensor = torch.tensor(x_train_seq)
        batch_size = 128
        for _ in range(8):
            perm = torch.randperm(x_train_tensor.size(0))
            for i in range(0, x_train_tensor.size(0), batch_size):
                idx_batch = perm[i : i + batch_size]
                batch = x_train_tensor[idx_batch]
                recon = model(batch)
                loss = loss_fn(recon, batch)
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

        model.eval()
        with torch.no_grad():
            train_recon = model(torch.tensor(x_train_seq))
            train_err = torch.mean((torch.tensor(x_train_seq) - train_recon) ** 2, dim=(1, 2)).cpu().numpy()

            test_tensor = torch.tensor(test_seq.x)
            test_recon = model(test_tensor)
            test_err = torch.mean((test_tensor - test_recon) ** 2, dim=(1, 2)).cpu().numpy()

        lstm_risk = normalize_scores(train_err, test_err)
        results["LSTMAutoEncoder"] = metrics(test_seq.y, lstm_risk)
    else:
        results["LSTMAutoEncoder"] = {
            "roc_auc": 0.0,
            "pr_auc": 0.0,
            "f1_best": 0.0,
            "best_threshold": 0.5,
        }

    return results


if __name__ == "__main__":
    dataset_path = "data/synthetic_web_auth_logs.csv"
    all_results = benchmark(dataset_path)
    ranked = sorted(all_results.items(), key=lambda x: (x[1]["pr_auc"], x[1]["f1_best"]), reverse=True)
    winner = ranked[0][0]
    output = {"dataset": dataset_path, "results": all_results, "winner_by_pr_auc": winner}
    print(json.dumps(output, indent=2))
    with open("technique_benchmark.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
