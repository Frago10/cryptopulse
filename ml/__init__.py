"""
CryptoPulse — ML layer (Fase 5).

Submodules:
  * sentiment.vader_scorer   — VADER polarity scoring on Reddit posts.
  * anomaly.price_anomalies  — Hybrid (rolling z-score + IsolationForest)
                               anomaly detection on hourly OHLCV.

Both persist results to the `ml` schema in Postgres. dbt consumes these
tables as sources and builds `mart_anomaly_alerts` downstream.
"""
