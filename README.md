# CryptoPulse

> Real-time crypto market intelligence platform — data engineering end-to-end portfolio project.

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker)
![dbt](https://img.shields.io/badge/dbt-1.7-FF694B?logo=dbt)
![Airflow](https://img.shields.io/badge/Airflow-2.9-017CEE?logo=apacheairflow)
![PowerBI](https://img.shields.io/badge/Power%20BI-F2C811?logo=powerbi&logoColor=black)

**CryptoPulse** captures the crypto market pulse in real time, processes it with a modern medallion architecture (bronze / silver / gold), applies ML to detect price anomalies and sentiment signals, and exposes everything through two visualization layers: an executive Power BI dashboard and a public Streamlit web app.

## Highlights

- **Hybrid ingestion:** real-time Binance WebSocket + batch REST (CoinGecko, Reddit, Fear&Greed Index).
- **Medallion architecture:** raw Parquet on MinIO (bronze), cleaned with dbt in Postgres (silver), star schema for BI (gold).
- **Machine Learning:** Isolation Forest for anomaly detection + VADER sentiment on Reddit posts.
- **Orchestrated with Airflow:** batch DAGs, ML retraining, data-quality checks with Great Expectations.
- **Two visualization layers:** Power BI (.pbix) executive dashboard + public Streamlit web app.
- **Telegram alerts** when anomalies are detected.
- **Fully containerized** with Docker Compose — `docker compose up` and you have the full stack.

## Architecture

See `docs/ARCHITECTURE.md` for the detailed diagram and `CryptoPulse_Roadmap.md` for the full build plan.

## Quickstart

```bash
git clone <this-repo> && cd cryptopulse
cp .env.example .env          # edit secrets
make up                       # docker compose up -d
make batch-run                # first ingestion
make dbt-run && make dbt-test # transformations
make streamlit                # local dashboard
```

## Status

Work in progress — built phase by phase. Current phase: **0 — Infrastructure setup**.

## Author

Frago — jeanpaulfrago10@gmail.com
