# User Behaviour Anomaly PDF Alignment

This document maps implementation status to the referenced PDF (`User Behaviour Anomaly.pdf`).

## Architecture Flow

From the PDF:
1. Spring Boot backend collects and forwards user events.
2. Python anomaly service trains model(s) and exposes `/detect`.
3. Spring Boot consumes score and enforces policy, including audit logging.

Current status in this repository:
1. Implemented: `POST /enterprise/login` receives user risk signals.
2. Implemented: Python service exposes `POST /detect` and returns anomaly risk.
3. Implemented: Spring decision engine returns `ALLOW`, `MFA_CHALLENGE`, or `BLOCK`.
4. Implemented: structured decision audit log line on each request.

## Algorithm Mapping

From the PDF:
- Isolation Forest
- LSTM Autoencoder
- Local Outlier Factor (LOF)
- Categorical Mixture Models

Current status:
- Isolation Forest: implemented in `ml-risk-engine/train.py`.
- Autoencoder-based detector: implemented (currently feed-forward autoencoder).
- LSTM Autoencoder: not yet implemented.
- LOF: not yet implemented.
- Categorical Mixture Models: not yet implemented.

## Suggested Next Build Iteration

1. Add sequence event windows and replace feed-forward autoencoder with LSTM autoencoder.
2. Add optional LOF component and weighted ensemble in `/detect`.
3. Add role/profile categorical scoring component for categorical behavior shifts.
