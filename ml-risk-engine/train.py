import json
import os
from typing import Tuple

import joblib
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, classification_report, f1_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.ensemble import RandomForestClassifier

from feature_engineering import build_training_frame


NUM_COLS = ["login_hour", "failed_attempts", "country_changed", "device_changed", "ip_last_octet"]
CAT_COLS = ["login_status", "country_code"]


def evaluate(y_true: np.ndarray, prob: np.ndarray, threshold: float) -> Tuple[float, float, float]:
    pred = (prob >= threshold).astype(int)
    return (
        float(roc_auc_score(y_true, prob)),
        float(average_precision_score(y_true, prob)),
        float(f1_score(y_true, pred)),
    )


def best_threshold(y_true: np.ndarray, prob: np.ndarray) -> float:
    best_t = 0.5
    best_f1 = -1.0
    for t in np.arange(0.10, 0.91, 0.01):
        f1 = f1_score(y_true, (prob >= t).astype(int))
        if f1 > best_f1:
            best_f1 = f1
            best_t = float(t)
    return best_t


def main() -> None:
    data_path = os.environ.get("TRAIN_DATA_PATH", "data/synthetic_web_auth_logs_v2.csv")
    x, y = build_training_frame(data_path)

    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=0.20, random_state=42, stratify=y
    )
    x_fit, x_val, y_fit, y_val = train_test_split(
        x_train, y_train, test_size=0.25, random_state=42, stratify=y_train
    )

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), NUM_COLS),
            ("cat", OneHotEncoder(handle_unknown="ignore"), CAT_COLS),
        ]
    )

    rf_pipeline = Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            (
                "rf",
                RandomForestClassifier(
                    n_estimators=450,
                    max_depth=12,
                    min_samples_leaf=3,
                    class_weight="balanced_subsample",
                    random_state=42,
                    n_jobs=-1,
                ),
            ),
        ]
    )
    lr_pipeline = Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            (
                "lr",
                LogisticRegression(
                    class_weight="balanced",
                    max_iter=300,
                    C=1.1,
                    solver="lbfgs",
                    random_state=42,
                ),
            ),
        ]
    )

    rf_pipeline.fit(x_fit, y_fit)
    lr_pipeline.fit(x_fit, y_fit)

    val_rf = rf_pipeline.predict_proba(x_val)[:, 1]
    val_lr = lr_pipeline.predict_proba(x_val)[:, 1]

    rf_auc = roc_auc_score(y_val, val_rf)
    lr_auc = roc_auc_score(y_val, val_lr)
    w_sum = rf_auc + lr_auc
    rf_weight = float(rf_auc / w_sum) if w_sum > 0 else 0.7
    lr_weight = float(lr_auc / w_sum) if w_sum > 0 else 0.3
    val_risk = (rf_weight * val_rf) + (lr_weight * val_lr)
    threshold = best_threshold(y_val.to_numpy(), val_risk)

    test_rf = rf_pipeline.predict_proba(x_test)[:, 1]
    test_lr = lr_pipeline.predict_proba(x_test)[:, 1]
    test_risk = (rf_weight * test_rf) + (lr_weight * test_lr)
    test_pred = (test_risk >= threshold).astype(int)

    roc_auc, pr_auc, f1 = evaluate(y_test.to_numpy(), test_risk, threshold)
    metrics = {
        "dataset_path": data_path,
        "samples": int(len(x)),
        "anomaly_rate": float(y.mean()),
        "rf_weight": rf_weight,
        "lr_weight": lr_weight,
        "threshold": threshold,
        "roc_auc": roc_auc,
        "pr_auc": pr_auc,
        "f1": f1,
        "classification_report": classification_report(
            y_test.to_numpy(), test_pred, output_dict=True, zero_division=0
        ),
    }

    bundle = {
        "rf_pipeline": rf_pipeline,
        "lr_pipeline": lr_pipeline,
        "rf_weight": rf_weight,
        "lr_weight": lr_weight,
        "threshold": threshold,
        "metrics": metrics,
        "feature_columns": NUM_COLS + CAT_COLS,
    }
    joblib.dump(bundle, "risk_model_bundle.pkl")
    with open("training_metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    print("Training complete on new dataset.")
    print(json.dumps({"roc_auc": roc_auc, "pr_auc": pr_auc, "f1": f1, "threshold": threshold}, indent=2))


if __name__ == "__main__":
    main()
