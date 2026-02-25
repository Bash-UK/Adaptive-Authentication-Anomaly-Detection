# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog and uses Semantic Versioning.

## [2.0.0] - 2026-02-25
### Added
- Product-style multi-page frontend navigation (`Dashboard`, `Simulation`, `User Graphs`, `Risk Events`).
- Dashboard overview cards with quick-start guidance.
- Searchable graph user selection with live match list and Enter-to-load behavior.
- Inline graph point tooltip for clearer risk/confidence hover insights.

### Changed
- Map-based location simulation UX and visual theme refinements.
- Country change derivation now uses reverse-geocoded previous/current country comparison.
- Graph control flow streamlined to a single user-graph load action.

## [1.0.0] - 2026-02-25
### Added
- Unsupervised real-time anomaly detection engine (per-user baseline + global Isolation Forest).
- Spring adaptive authentication policy layer with `ALLOW` / `MFA_CHALLENGE` / `BLOCK`.
- React demo frontend with simulation console and interactive anomaly timeline graph.
- PostgreSQL-backed persistence for user state, global vectors, and risk event history.
- User history and tracked-users APIs for graph visualization.
- Full project documentation and benchmark summaries.

### Changed
- Improved graph UX with moving average, anomaly markers, and user selection in graph panel.
- Country-change is now automatically derived from previous/current location input.
