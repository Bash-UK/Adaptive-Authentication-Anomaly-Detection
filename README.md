# Enterprise Adaptive Anomaly Engine

Unsupervised, real-time user behavior anomaly detection system for adaptive authentication.

This repository contains:
- `demo-frontend` (React + Nginx) for interactive simulation and risk graphing.
- `java-idp-enterprise` (Spring Boot) for policy orchestration and adaptive auth decisions.
- `ml-risk-engine` (FastAPI + scikit-learn) for real-time anomaly scoring with persistence.

## What It Does
- Ingests login behavior events (user, country, device, login status, hour, failed attempts, IP).
- Scores anomalies using a hybrid unsupervised model:
  - Per-user adaptive baseline deviation.
  - Global rolling Isolation Forest outlier score.
- Applies IAM policy boosts and thresholds to output:
  - `ALLOW`
  - `MFA_CHALLENGE`
  - `BLOCK`
- Persists state and risk timeline in PostgreSQL for continuity and graph visualization.

## v2.0.0 Highlights
- Multi-page frontend navigation: `Dashboard`, `Simulation`, `User Graphs`, `Risk Events`.
- Dashboard overview cards with quick-start guidance.
- Map-based location simulation with previous/current point selection.
- Country change derived automatically from reverse-geocoded previous/current locations.
- Searchable graph user selection with Enter-to-load and improved point hover tooltip.

## Quick Start
### Prerequisites
- Docker + Docker Compose
- Existing PostgreSQL instance on `localhost:5432`
- A dedicated DB for this project (default used here: `anomaly_engine_rt`)

### 1) Create Dedicated DB (once)
```bash
docker exec postgres psql -U postgres -c "CREATE DATABASE anomaly_engine_rt;"
```

### 2) Start Stack
```bash
docker compose up --build -d
```

### 3) Access Services
- Frontend: `http://localhost:8088`
- Java API: `http://localhost:9091`
- ML API: `http://localhost:9092`

## Core Endpoints
### Java Backend (`9091`)
- `POST /enterprise/login` -> final adaptive auth decision.
- `GET /enterprise/user/{userId}/history?limit=70` -> timeline points for graph.
- `GET /enterprise/users?limit=300` -> tracked users for graph selector.
- `GET /enterprise/version` -> backend version metadata.

### ML Engine (`9092`)
- `POST /detect` -> unsupervised risk + confidence + model components.
- `GET /history/{user_id}?limit=70` -> persisted ML risk timeline.
- `GET /users?limit=300` -> known user IDs from state/history.
- `GET /health` -> model readiness + persistence mode.
- `GET /version` -> ML service version metadata.

## Example API Call
```bash
curl -X POST http://localhost:9091/enterprise/login \
  -H "Content-Type: application/json" \
  -d '{
    "userId":"u-1001",
    "deviceId":"dev-home-01",
    "countryCode":"US",
    "loginStatus":"Success",
    "loginHour":10,
    "loginHourNormalized":0.43,
    "newDeviceFlag":0,
    "countryChangeFlag":0,
    "geoDistanceNormalized":0.0,
    "ipRiskScore":0.1,
    "failedAttemptsLastHour":0,
    "ipAddress":"192.168.1.10"
  }'
```

## Current Runtime Model (Active)
- Type: `unsupervised-realtime-user-baseline-plus-isolation-forest`
- Offline training required at inference: `No`
- Persistence: PostgreSQL (or memory-only fallback if DB unavailable)

## Benchmarks (Offline, Historical Artifacts)
From `ml-risk-engine/technique_benchmark.json` (dataset: `synthetic_web_auth_logs.csv`):
- IsolationForest: ROC-AUC `0.4333`, PR-AUC `0.1577`, best F1 `0.2773`
- LocalOutlierFactor: ROC-AUC `0.7775`, PR-AUC `0.5281`, best F1 `0.6152` (winner by PR-AUC)
- CategoricalMixture: ROC-AUC `0.7241`, PR-AUC `0.4793`, best F1 `0.5352`
- LSTMAutoEncoder: ROC-AUC `0.5538`, PR-AUC `0.5117`, best F1 `0.5000`

From `ml-risk-engine/lstm_sequence_benchmark.json` (dataset: `synthetic_web_auth_logs_v2.csv`):
- LOF baseline: ROC-AUC `0.8291`, PR-AUC `0.4434`, F1 `0.4527`
- LSTM autoencoder: ROC-AUC `0.6134`, PR-AUC `0.1463`, F1 `0.2224`
- LSTM autoencoder + LOF latent: ROC-AUC `0.6122`, PR-AUC `0.1469`, F1 `0.2238`

Note:
- `ml-risk-engine/training_metrics.json` is a legacy supervised experiment artifact and not the active production inference path.

## Documentation
- Full technical documentation: [`docs/PROJECT_DOCUMENTATION.md`](docs/PROJECT_DOCUMENTATION.md)
- PDF traceability notes: [`docs/PDF_ALIGNMENT.md`](docs/PDF_ALIGNMENT.md)

## Docker Build Optimization
- Python dependencies are installed from `ml-risk-engine/requirements.txt` in a stable layer.
- Rebuilds reuse dependency cache unless `requirements.txt` changes.

## Versioning
- Project version file: `VERSION`
- Changelog: `CHANGELOG.md`
- Current release: `2.0.0`
- Current service defaults:
  - Backend version from `java-idp-enterprise/src/main/resources/application.yml` (`app.version`)
  - ML version from `APP_VERSION` in `docker-compose.yml`
