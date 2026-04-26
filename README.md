# CryptoPulse

> End-to-end data platform for crypto market intelligence — streaming + batch ingestion, medallion lakehouse, ML, BI dashboarding, alerting, and CI/CD.

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker)
![Postgres](https://img.shields.io/badge/Postgres-15-336791?logo=postgresql)
![Redpanda](https://img.shields.io/badge/Redpanda-Kafka-FF3850)
![dbt](https://img.shields.io/badge/dbt-1.8-FF694B?logo=dbt)
![Airflow](https://img.shields.io/badge/Airflow-2.9-017CEE?logo=apacheairflow)
![PowerBI](https://img.shields.io/badge/Power%20BI-F2C811?logo=powerbi&logoColor=black)
![Streamlit](https://img.shields.io/badge/Streamlit-1.35-FF4B4B?logo=streamlit)

CryptoPulse pipes 8 crypto symbols of live tick data from Binance, joins it with hourly market snapshots (CoinGecko), social signals (Reddit), and the Fear & Greed Index, runs ML to surface anomalous hours, and serves it through a Power BI dashboard, a Streamlit lab app with an LLM "explain this alert" agent, and a Telegram alert bot.

It is built and operated as a portfolio project: every phase is reproducible from `git clone` with a single `docker compose up` plus a handful of `make` targets.

---

## What it does

| Capability | How |
|---|---|
| **Real-time ticks** | Binance WebSocket → Redpanda topic → Postgres `raw.ticks` (sub-second latency, 8 symbols) |
| **Hourly batch** | CoinGecko REST + Reddit API + Fear & Greed Index → MinIO (Parquet) + Postgres `raw.*` |
| **Medallion** | dbt staging → marts (`fact_prices_hourly`, `fact_market_snapshot`, `fact_sentiment_daily`, `dim_coin`) |
| **ML** | VADER sentiment on Reddit; z-score + IsolationForest consensus for price anomalies |
| **Data quality** | Great Expectations suites on raw + gold (range/whitelist/freshness) |
| **Orchestration** | 3 Airflow DAGs: hourly (batch + ML + alerts), daily (VADER), streaming health probe |
| **BI** | Power BI on a stable `bi.*` view layer that decouples reporting from dbt models |
| **Streamlit Lab** | Live tick tail + Alert Explainer agent powered by Anthropic Claude |
| **Alerts** | Telegram bot, idempotent dedup table, optional LLM-enriched message body |
| **CI/CD** | GitHub Actions: ruff lint + pytest on push/PR |

---

## Architecture

```
                                  ┌─────────────────────────┐
   Binance WS ─── Redpanda ─────► │  raw.ticks (Postgres)   │
                                  └─────────┬───────────────┘
                                            │
   CoinGecko REST ─┐                        │  ┌────────────────────────┐
   Reddit API     ─┼─► MinIO (Parquet) ───► ├─►│  raw.coingecko_markets │
   Fear&Greed     ─┘     bronze             │  │  raw.reddit_posts      │
                                            │  │  raw.fear_greed        │
                                            │  └────────────┬───────────┘
                                            │               │
                                            ▼               ▼
                                  ┌─────────────────────────────────────┐
                                  │  dbt staging  (silver)              │
                                  │      └─► dbt marts (gold)           │
                                  │            ├ fact_prices_hourly     │
                                  │            ├ fact_market_snapshot   │
                                  │            ├ fact_sentiment_daily   │
                                  │            ├ mart_anomaly_alerts    │
                                  │            └ dim_coin / dim_date    │
                                  └─────────┬─────────────┬─────────────┘
                                            │             │
                  ┌─────────────────────────┘             │
                  ▼                                       ▼
       ┌────────────────────┐                  ┌─────────────────────┐
       │  ML jobs           │                  │  bi.* views         │
       │  ├ vader_scorer    │                  │  (BI abstraction)   │
       │  └ price_anomalies │──► ml.*          └────────┬────────────┘
       └────────────────────┘                           │
                                            ┌──────────┼──────────────┐
                                            ▼          ▼              ▼
                                     ┌──────────┐ ┌──────────┐ ┌──────────────┐
                                     │ Power BI │ │ Streamlit│ │ Telegram bot │
                                     │  .pbix   │ │   Lab    │ │ (Airflow)    │
                                     └──────────┘ └──────────┘ └──────────────┘

   Airflow orchestrates batch + ML + GE + alerts; streaming runs as long-lived processes.
```

See [`docs/RUNBOOK.md`](docs/RUNBOOK.md) for the operational runbook and `docs/CryptoPulse_Roadmap.md` for the original build plan.

---

## Stack

| Layer | Tool |
|---|---|
| Streaming | Binance WebSocket, Redpanda (Kafka-compatible), confluent-kafka |
| Batch ingestion | Python (requests, praw), boto3 → MinIO |
| Lakehouse | MinIO (S3-compat), Postgres 15 |
| Transformation | dbt-postgres 1.8, dbt-utils, dbt-date |
| ML | scikit-learn (IsolationForest), vaderSentiment, joblib |
| Orchestration | Apache Airflow 2.9 (LocalExecutor) |
| Data quality | Great Expectations 0.18 |
| BI | Power BI Desktop |
| Streamlit Lab | streamlit, plotly, anthropic SDK (Claude Haiku 4.5) |
| Alerting | Telegram Bot API (HTTP) |
| CI | GitHub Actions (ruff + pytest) |
| Containerization | Docker Compose |

---

## Quick start (5 minutes)

```powershell
git clone <this-repo> && cd cryptopulse
cp .env.example .env                      # set POSTGRES_PASSWORD, REDDIT keys, TELEGRAM, ANTHROPIC
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

docker compose up -d                      # postgres + minio + redpanda + airflow

# Bootstrap the warehouse
python -m ingestion.utils.pg_bootstrap    # applies 02_, 03_, 04_, 05_ SQL scripts

# First end-to-end pipeline run
python -m ingestion.batch.coingecko_loader
python -m ingestion.batch.reddit_loader
python -m ingestion.batch.fng_loader
cd dbt_project && dbt deps && dbt run && dbt test && cd ..
python -m ml.sentiment.vader_scorer
python -m ml.anomaly.price_anomalies
cd dbt_project && dbt run --select mart_anomaly_alerts && cd ..

# Fire the dashboards
streamlit run dashboard/streamlit_app.py  # http://localhost:8501
# Open dashboard/powerbi/cryptopulse.pbix in Power BI Desktop
```

For Linux/macOS users, every command above also has a `make` target (see `make help`).

---

## Project structure

```
cryptopulse/
├── airflow/                # 3 DAGs + plugin with task helpers
├── alerts/                 # Telegram notifier (Phase 10)
├── dashboard/
│   ├── powerbi/            # queries.m, measures.dax, layout_spec.md
│   ├── streamlit_app.py    # multipage Streamlit Lab
│   ├── pages/              # Live Tick Tail · Alert Explainer (LLM)
│   └── lib/                # db.py · llm.py
├── data/                   # local volumes (gitignored)
├── dbt_project/
│   ├── models/staging/     # 6 staging models
│   └── models/marts/
│       ├── core/           # dim_coin, dim_date, fact_*
│       └── analytics/      # mart_anomaly_alerts, mart_top_movers, mart_social_vs_price
├── docs/                   # architecture, runbook, roadmap
├── ingestion/
│   ├── batch/              # coingecko, reddit, fng loaders
│   ├── streaming/          # Binance producer + Redpanda consumer
│   ├── sql/init/           # 01_init_schemas → 05_alerts_tables
│   └── utils/              # config (pydantic-settings), pg_client, minio_client, logging
├── ml/
│   ├── anomaly/            # z-score + IsolationForest + consensus
│   └── sentiment/          # VADER scorer
├── quality/                # Great Expectations suites + checkpoint runner
├── tests/                  # pytest unit tests
├── .github/workflows/ci.yml
├── Makefile
├── docker-compose.yml
├── pytest.ini
└── requirements*.txt
```

---

## Phases

| Phase | Deliverable | Status |
|---|---|---|
| 1 | Infrastructure (`docker compose`, schemas, `pg_bootstrap`) | ✅ |
| 2 | Streaming ingestion (Binance → Redpanda → Postgres) | ✅ |
| 3 | Batch ingestion (CoinGecko, Reddit, F&G) + MinIO | ✅ |
| 4 | dbt staging + marts (silver/gold) | ✅ |
| 5 | ML (VADER + price anomalies + `mart_anomaly_alerts`) | ✅ |
| 6 | Airflow DAGs (hourly, daily, streaming health) | ✅ |
| 7 | Great Expectations data quality | ✅ |
| 8 | Power BI dashboard (4 pages, 39 DAX measures, 5 `bi.*` views) | ✅ |
| 9 | Streamlit Lab (Live Tail + LLM Alert Explainer) | ✅ |
| 10 | Telegram alerts + GitHub Actions CI | ✅ |
| 11 | README + e2e validation | ✅ |

---

## Demos

| | |
|---|---|
| **Power BI** — 4-page executive dashboard | `dashboard/powerbi/cryptopulse.pbix` |
| **Streamlit Lab** — live tail + Claude-powered alert explainer | `streamlit run dashboard/streamlit_app.py` |
| **Telegram** — formatted anomaly notifications with optional LLM summary | trigger via Airflow or `python -m alerts.telegram_notifier` |

Add `docs/screenshots/` to drop demo images and reference them here.

---

## Highlights for reviewers

- **Decoupled BI layer.** Power BI never queries dbt models directly; it goes through `bi.*` views (`ingestion/sql/init/04_bi_views.sql`). When dbt renames a column, only the view changes — the `.pbix` keeps working.
- **Idempotent everything.** SQL scripts use `CREATE … IF NOT EXISTS` / `CREATE OR REPLACE`. Telegram dedup uses an `alert_key` primary key. dbt models are `materialized='table'` and rebuilt cleanly. You can blow up volumes and re-run.
- **Honest secrets handling.** `.env` is gitignored; `.env.example` is the contract; `pydantic-settings` reads it once into a typed `settings` object — no `os.getenv` strewn around the codebase.
- **Two-tier observability.** Airflow shows DAG health; the Streamlit `Live Tick Tail` page shows ticker freshness in real time with a traffic-light per symbol.
- **CI gates the diff.** `.github/workflows/ci.yml` runs ruff + pytest on every push/PR.

---

## Documentation

- [`docs/RUNBOOK.md`](docs/RUNBOOK.md) — operational runbook + every gotcha encountered, with fixes.
- [`docs/CryptoPulse_Roadmap.md`](docs/CryptoPulse_Roadmap.md) — original 11-phase build plan.
- [`dashboard/powerbi/README.md`](dashboard/powerbi/README.md) — Power BI assembly guide.
- [`dashboard/README.md`](dashboard/README.md) — Streamlit Lab guide.

---

## Author

**Frago** — `jeanpaulfrago10@gmail.com`

Built as a portfolio project to showcase end-to-end data engineering chops: streaming, batch, lakehouse, modeling, ML, orchestration, quality, BI, and AI integration.
