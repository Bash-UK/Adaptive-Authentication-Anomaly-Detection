# Project Documentation: Enterprise Adaptive Anomaly Engine

## 1. Project Overview
This project implements an adaptive authentication risk engine focused on unsupervised, real-time user behavior anomaly detection.

It is designed for IAM-style decisioning:
- low risk -> allow
- medium risk -> step-up authentication (MFA)
- high risk -> block

The system is split into three services:
- React frontend demo (`demo-frontend`)
- Spring Boot backend policy/API gateway (`java-idp-enterprise`)
- FastAPI ML engine (`ml-risk-engine`)

## 2. High-Level Architecture
1. User submits login context from frontend.
2. Frontend sends event to Java backend (`/enterprise/login`).
3. Java backend forwards event to ML engine (`/detect`).
4. ML engine returns `risk`, `confidence`, and component breakdown.
5. Java applies IAM policy boosts and thresholds.
6. Java returns final action (`ALLOW` / `MFA_CHALLENGE` / `BLOCK`).
7. Frontend fetches historical risk timeline and tracked users for graph UX.

## 3. Repository Structure
- `demo-frontend/`
  - React Vite app and Nginx container setup.
- `java-idp-enterprise/`
  - Spring API, decision policy logic, request validation.
- `ml-risk-engine/`
  - Unsupervised real-time anomaly engine, state persistence, benchmark scripts.
- `docs/`
  - Additional documentation and traceability notes.
- `docker-compose.yml`
  - Multi-service orchestration.

## 4. Services and Ports
- Frontend: `http://localhost:8088`
- Java backend: `http://localhost:9091`
- ML engine: `http://localhost:9092`

## 5. Data Flow and Runtime Sequence
### 5.1 Input Collection (Frontend)
Frontend captures user-friendly fields:
- `userId`
- `deviceId`
- previous and current country (2-letter)
- login status
- login hour
- device changed
- failed attempts
- IP address

It derives compatibility features (e.g., normalized fields) and computes country change automatically from previous/current country.

### 5.2 Backend Decision Orchestration
Java endpoint:
- `POST /enterprise/login`

Java forwards to ML with:
- `userId`
- behavioral context fields
- feature compatibility fields

ML response:
- `risk` (model risk, 0-1)
- `confidence` (0-1)
- component breakdown

Java then applies policy boosts and thresholds from `application.yml` to produce final action.

### 5.3 History and User Graph
- Java exposes `GET /enterprise/user/{userId}/history`
- Java exposes `GET /enterprise/users`
- Frontend uses these for graph timeline and user selector.

## 6. Active Algorithm and Technique
## 6.1 Model Type
Active inference model is:
- `unsupervised-realtime-user-baseline-plus-isolation-forest`

No supervised class labels are required for runtime inference.

## 6.2 Hybrid Scoring Components
### A) Per-user adaptive baseline risk
Engine keeps evolving user profile:
- seen countries/devices
- login hour history
- inter-login gap history
- failed attempts history
- geo jump history
- fail streak

Deviation/novelty features are scored with robust statistics (median/MAD based deviations and novelty flags).

### B) Global outlier risk (Isolation Forest)
A rolling global feature buffer is maintained.
Isolation Forest is fit/refit online:
- `n_estimators=240`
- contamination target ~`0.10`
- refit after enough samples and every fixed interval

Global risk is normalized via percentile mapping on model scores.

### C) Final ML risk
Weighted blend:
- `risk = 0.65 * user_risk + 0.35 * global_risk`

Confidence blends:
- user history maturity
- agreement between user/global components

## 7. Policy Layer (Java)
After ML risk is returned, Java policy adds context boosts:
- new device
- country changed
- long geo distance
- IP risk bands
- failed attempts bands
- odd login hour

Thresholds (defaults):
- high: `0.75` -> `BLOCK`
- moderate: `0.45` -> `MFA_CHALLENGE`
- else `ALLOW`

If confidence is below floor and action is `ALLOW`, action is elevated to `MFA_CHALLENGE`.

Configured in:
- `java-idp-enterprise/src/main/resources/application.yml`

## 8. Persistence and Database
ML persistence uses PostgreSQL (or memory fallback).

Expected DB:
- `anomaly_engine_rt`

Schema:
- `anomaly_engine.user_behavior_state`
- `anomaly_engine.global_feature_buffer`
- `anomaly_engine.user_risk_events`

Stored data:
- per-user state snapshots
- rolling global vectors
- per-event risk history for timeline graph

## 9. API Reference
## 9.1 Java (`9091`)
- `POST /enterprise/login`
  - request: login context + compatibility features
  - response: action, finalRisk, modelRisk, confidence, reasons
- `GET /enterprise/user/{userId}/history?limit=60`
  - response: timeline points
- `GET /enterprise/users?limit=200`
  - response: tracked users

## 9.2 ML (`9092`)
- `POST /detect`
  - response: risk, confidence, components, state, model metadata
- `GET /history/{user_id}?limit=60`
- `GET /users?limit=200`
- `GET /health`

## 10. Setup and Run
## 10.1 Prerequisites
- Docker + Docker Compose
- PostgreSQL available on host `localhost:5432`
- dedicated DB for this project (not shared app DB)

## 10.2 Create DB
```bash
docker exec postgres psql -U postgres -c "CREATE DATABASE anomaly_engine_rt;"
```

## 10.3 Start Stack
```bash
docker compose up --build -d
```

## 10.4 Stop Stack
```bash
docker compose down
```

## 10.5 Health Checks
```bash
curl http://localhost:9092/health
curl http://localhost:9091/enterprise/users?limit=20
```

## 11. Frontend UX Summary
Current frontend provides:
- simulation form for event generation
- decision panel showing action/risk/reasons
- graph panel with:
  - user selector
  - risk line
  - confidence line
  - moving average
  - threshold line
  - anomaly markers
  - metric cards and hover details

## 12. Benchmarking and Metrics
This repo includes offline benchmark artifacts used during exploration.

Important:
- These are offline evaluations on synthetic data.
- They are not direct SLA guarantees for live streaming production traffic.

### 12.1 Technique Benchmark (`technique_benchmark.json`)
Dataset: `ml-risk-engine/data/synthetic_web_auth_logs.csv`

| Technique | ROC-AUC | PR-AUC | Best F1 |
|---|---:|---:|---:|
| IsolationForest | 0.4333 | 0.1577 | 0.2773 |
| LocalOutlierFactor | 0.7775 | 0.5281 | 0.6152 |
| CategoricalMixture | 0.7241 | 0.4793 | 0.5352 |
| LSTMAutoEncoder | 0.5538 | 0.5117 | 0.5000 |

Winner by PR-AUC: `LocalOutlierFactor`

### 12.2 Sequence Benchmark (`lstm_sequence_benchmark.json`)
Dataset: `ml-risk-engine/data/synthetic_web_auth_logs_v2.csv`, sequence length 12

| Technique | ROC-AUC | PR-AUC | F1 |
|---|---:|---:|---:|
| LOF baseline | 0.8291 | 0.4434 | 0.4527 |
| LSTM autoencoder | 0.6134 | 0.1463 | 0.2224 |
| LSTM AE + LOF latent | 0.6122 | 0.1469 | 0.2238 |

### 12.3 Legacy Supervised Artifact (`training_metrics.json`)
Contains high offline supervised scores from earlier experimentation:
- ROC-AUC: `0.9533`
- PR-AUC: `0.8904`
- F1: `0.8605`

This is not the active runtime algorithm for current real-time unsupervised service.

## 13. Reproducing Benchmarks
From `ml-risk-engine/` (Python environment with required deps):

```bash
python benchmark_techniques.py
python lstm_sequence_pipeline.py
```

Outputs:
- `technique_benchmark.json`
- `lstm_sequence_benchmark.json`

## 14. Configuration
Main runtime configuration:
- `docker-compose.yml`
  - ML DSN and schema env vars
- `java-idp-enterprise/src/main/resources/application.yml`
  - policy thresholds and boosts

ML env variables:
- `ANOMALY_PG_ENABLED`
- `ANOMALY_DB_DSN`
- `ANOMALY_DB_SCHEMA`
- `ANOMALY_PG_VECTOR_KEEP`

## 15. Operational Notes
- ML engine gracefully falls back to memory mode if DB init/restore fails.
- Java has fallback MFA behavior when ML service is unreachable.
- Frontend can still submit events even if history endpoints are temporarily unavailable.

## 16. Limitations and Future Work
- Synthetic dataset only; real telemetry calibration is recommended before production.
- Add observability:
  - latency histograms
  - drift statistics
  - threshold tuning dashboard
- Add event schema versioning and stronger API contracts.
- Add integration tests for end-to-end decision and history flow.

## 17. Key Files
- `ml-risk-engine/realtime_engine.py`
- `ml-risk-engine/state_store.py`
- `ml-risk-engine/main.py`
- `java-idp-enterprise/src/main/java/enterprise/anomaly/controller/DemoController.java`
- `java-idp-enterprise/src/main/java/enterprise/anomaly/service/MlRiskClient.java`
- `java-idp-enterprise/src/main/resources/application.yml`
- `demo-frontend/src/App.jsx`
- `docker-compose.yml`
