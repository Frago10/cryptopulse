# CryptoPulse — Complete Guide

> Professional project manual. Designed so that both a technical reviewer and someone without a data engineering background can understand what the system does, why it is built this way, and how to operate it step by step.

---

## Table of contents

1. [Executive summary](#1-executive-summary)
2. [What problem does it solve?](#2-what-problem-does-it-solve)
3. [Tech stack explained](#3-tech-stack-explained)
4. [High-level architecture](#4-high-level-architecture)
5. [Step-by-step setup from scratch](#5-step-by-step-setup-from-scratch)
6. [Tour of the 11 phases](#6-tour-of-the-11-phases)
7. [Key functions and modules](#7-key-functions-and-modules)
8. [Day-to-day operations](#8-day-to-day-operations)
9. [Troubleshooting](#9-troubleshooting)
10. [Glossary for non-technical readers](#10-glossary-for-non-technical-readers)
11. [Next improvements](#11-next-improvements)

---

## 1. Executive summary

**CryptoPulse** is an end-to-end crypto market intelligence platform. It captures real-time prices from Binance, enriches them every hour with data from CoinGecko, Reddit, and the Fear & Greed Index, cleans and models them with dbt, applies machine learning to surface anomalous price moves and social sentiment, and delivers everything through three channels: an executive Power BI dashboard, an interactive Streamlit app with an AI agent that explains alerts, and automatic Telegram notifications.

It is built as a portfolio project demonstrating mastery of the core disciplines of modern data engineering: streaming, batch, lakehouse on a medallion architecture (bronze / silver / gold), dimensional modeling, applied ML, orchestration, data quality, BI, alerting, and CI/CD.

**In one sentence:** clone the repo, run `docker compose up`, and in less than an hour you have a fully operational end-to-end crypto data pipeline.

---

## 2. What problem does it solve?

Imagine you are a trader or analyst who needs to answer questions like:

- How healthy is the crypto market right now?
- Did Bitcoin make an anomalous move in the last hour? Why?
- Does Reddit sentiment lead or lag price?
- Which was the worst performer in the last 24h?

Today, that information lives scattered: prices on Binance, metrics on CoinGecko, sentiment on Reddit, indices on external sites. Consolidating it manually is slow and error-prone.

**CryptoPulse** automates that consolidation. It captures the data, unifies it, runs ML to highlight what matters, and presents it executively. If something relevant happens (for instance, an anomalous drop detected by two independent algorithms), it pushes a Telegram alert with explanation included — without you having to stare at a screen.

It is the "personal mini-Bloomberg for crypto" — built with open source tooling and runnable on a laptop.

---

## 3. Tech stack explained

Each tool has a specific role. Here is the accessible justification and the alternative we passed on.

### Ingestion layer

| Tool | What we use it for | Alternative we discarded |
|---|---|---|
| **Binance WebSocket** | Tick-by-tick price streaming (sub-second) | REST polling — much higher latency |
| **Redpanda** | Kafka-compatible broker to decouple producer and consumer | Apache Kafka — heavier to run on a laptop |
| **Python `confluent-kafka`** | Broker client, high throughput | `kafka-python` — slower |
| **`requests` / `praw`** | REST calls to CoinGecko and Reddit | `aiohttp` — unnecessary complexity for low volume |
| **`pydantic-settings`** | Typed configuration from `.env` | `os.getenv` scattered across the codebase |

### Storage layer

| Tool | What we use it for | Why |
|---|---|---|
| **MinIO** | Local S3-compatible object store (bronze layer) | Same API as AWS S3 — code would be identical in production |
| **PostgreSQL 15** | Main warehouse (silver + gold) | Supports JSONB, partitioning, rich indexes; dbt-postgres is mature |
| **Parquet** | Columnar compressed format for the data lake | Saves 5-10× space vs CSV, selective column reads |

### Transformation layer

| Tool | Role |
|---|---|
| **dbt-postgres** | Defines staging and mart models in versioned SQL with native testing and docs |
| **dbt-utils, dbt-date** | Standard macros (surrogate keys, date dim, etc.) |

### Machine Learning

| Tool | Used for |
|---|---|
| **scikit-learn — IsolationForest** | Unsupervised anomaly detection (no labels needed) |
| **Rolling z-score** | Classic statistical detector, complements IF |
| **Consensus rule** | Flags an anomaly as "strong" only if BOTH detectors agree → improves precision, lowers false positives |
| **VADER sentiment** | Fast lexicon-based sentiment over Reddit posts (compound score `[-1, +1]`) |

### Orchestration and quality

| Tool | Used for |
|---|---|
| **Apache Airflow 2.9** | Declarative DAGs: hourly (batch + ML + alerts), daily (VADER), streaming health probe |
| **Great Expectations 0.18** | Declarative data-quality validations: ranges, symbol whitelists, not-nulls |

### Visualization and communication

| Tool | Audience |
|---|---|
| **Power BI Desktop** | Executive stakeholders. 4-page dashboard with 39 DAX measures |
| **Streamlit + Plotly** | Technical analysts. Interactive, Python-native, deployable in one command |
| **Telegram Bot API** | Mobile-first: push notifications wherever you are |
| **Anthropic Claude (Haiku 4.5)** | Turns a raw alert into a natural-language explanation |

### CI/CD

| Tool | Used for |
|---|---|
| **Docker Compose** | Spins up the entire stack (Postgres, MinIO, Redpanda, Airflow) with a single command |
| **GitHub Actions** | Linter (ruff) + tests (pytest) on every push and pull request |

---

## 4. High-level architecture

### 4.1. Data flow diagram

```
                                  ┌─────────────────────────┐
   Binance WS ─── Redpanda ─────► │  raw.ticks (Postgres)   │   ◄── streaming
                                  └─────────┬───────────────┘
                                            │
   CoinGecko REST ─┐                        │
   Reddit API     ─┼─► MinIO (Parquet) ───► ├── raw.coingecko_markets
   Fear&Greed     ─┘     bronze             ├── raw.reddit_posts        ◄── batch
                                            └── raw.fear_greed
                                                  │
                                                  ▼
                                  ┌──────────────────────────────────┐
                                  │  dbt staging  (silver)           │
                                  │      └─► dbt marts (gold)        │
                                  │            ├ fact_prices_hourly  │
                                  │            ├ fact_market_snapshot│
                                  │            ├ fact_sentiment_daily│
                                  │            ├ mart_anomaly_alerts │
                                  │            └ dim_coin / dim_date │
                                  └─────────┬─────────────┬──────────┘
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
```

### 4.2. Why medallion (bronze / silver / gold)

**Bronze** = raw data exactly as it arrived, untouched. Lives in MinIO as Parquet (hourly snapshots) and in Postgres `raw.*` for fast access. If you find a bug in a downstream transformation, you can always go back to bronze and reprocess.

**Silver** = clean, typed data — one row per event. This is where dbt applies dedup, casting, and symbol normalization. The `staging` tables live here.

**Gold** = analysis-ready data. Classic dimensional model: facts (numeric events) + dims (descriptive attributes). This is what a BI tool can consume directly.

**BI layer (`bi.*` views)** = a shield between dbt and the visualization tool. If dbt renames a column in a mart, you only update the view — the analyst's `.pbix` keeps working. It's the "presentation decoupling" pattern applied to BI.

### 4.3. Streaming vs batch — why both

- **Streaming (Binance):** prices change in milliseconds. Any latency is noise. WebSocket + Redpanda + Python consumer solves it.
- **Batch (CoinGecko, Reddit, F&G):** market cap, supply, sentiment — slow-moving data. REST polling every hour is enough and rate-limit friendly.

Mixing both disciplines in one project is exactly what real platforms do. It is not pure-streaming or pure-batch: it is a hybrid pipeline.

---

## 5. Step-by-step setup from scratch

We assume Windows + PowerShell. Everything is valid on Linux/macOS by adjusting paths.

### 5.1. Prerequisites

| Software | Min version | How to verify |
|---|---|---|
| Docker Desktop | 4.20+ | `docker --version` |
| Python | 3.11 | `python --version` |
| Git | 2.40+ | `git --version` |
| Power BI Desktop | latest | (optional, only Phase 8) |

Optional accounts (leave blank if you don't use them — the system still runs):

- Reddit Dev App: https://www.reddit.com/prefs/apps (Phase 3)
- Anthropic API key: https://console.anthropic.com/settings/keys (Phase 9-10 LLM)
- Telegram bot token: chat with @BotFather (Phase 10)

### 5.2. Clone and configure environment

```powershell
git clone <your-repo> cryptopulse
cd cryptopulse

# Copy the template and edit it with your secrets
Copy-Item .env.example .env
notepad .env
```

Minimum variables to set in `.env`:

```ini
POSTGRES_PASSWORD=cryptopulse_local_2026
ANTHROPIC_API_KEY=sk-ant-...      # optional Phase 9-10
ANTHROPIC_MODEL=claude-haiku-4-5-20251001
TELEGRAM_BOT_TOKEN=1234:ABC...    # optional Phase 10
TELEGRAM_CHAT_ID=123456789        # optional Phase 10
REDDIT_CLIENT_ID=...              # optional, improves social data
REDDIT_CLIENT_SECRET=...
```

### 5.3. Python environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 5.4. Bring up the infrastructure

```powershell
docker compose up -d
docker compose ps                  # everything Up (healthy)
```

Services available after `up`:

| Service | URL | Credentials |
|---|---|---|
| Postgres | `localhost:5432` | `cryptopulse / <POSTGRES_PASSWORD>` |
| MinIO API | `http://localhost:9000` | `minio / minio12345` |
| MinIO Console | `http://localhost:9001` | same |
| Redpanda | `localhost:9092` | no auth |
| Redpanda UI | `http://localhost:8080` | no auth |
| Airflow UI | `http://localhost:8081` | `admin / admin` |

### 5.5. Database bootstrap

```powershell
python -m ingestion.utils.pg_bootstrap
```

This applies the SQL scripts in `ingestion/sql/init/` (except `01_init_schemas.sql`, which Postgres already ran in its initial entrypoint).

### 5.6. First end-to-end pipeline run

```powershell
# Batch ingestion (public APIs do not require keys)
python -m ingestion.batch.coingecko_loader
python -m ingestion.batch.fng_loader
python -m ingestion.batch.reddit_loader   # requires REDDIT_CLIENT_ID

# Silver/gold transformation
cd dbt_project
dbt deps
dbt run
dbt test
cd ..

# ML
python -m ml.sentiment.vader_scorer
python -m ml.anomaly.price_anomalies
cd dbt_project ; dbt run --select mart_anomaly_alerts ; cd ..

# Data quality
python -m quality.run_checkpoint

# BI views
python -m ingestion.utils.pg_bootstrap --only 04_bi_views.sql

# Streaming (in another terminal, leave running)
python -m ingestion.streaming.create_topics
python -m ingestion.streaming.binance_producer
# in another terminal:
python -m ingestion.streaming.redpanda_consumer
```

### 5.7. Launch the apps

```powershell
# Streamlit Lab
streamlit run dashboard/streamlit_app.py
# Open http://localhost:8501

# Power BI: open dashboard/powerbi/cryptopulse.pbix manually
# (follow dashboard/powerbi/README.md the first time)

# Telegram smoke test
python -c "from alerts.telegram_notifier import send_to_telegram; print(send_to_telegram('<b>Test</b>', dry_run=False))"
```

---

## 6. Tour of the 11 phases

Each phase is self-contained. We built the project phase by phase, validating each before advancing — so the portfolio tells a story and every commit makes sense.

### Phase 1 — Infrastructure

**Goal:** stand up the reproducible base stack.

**Deliverables:**
- `docker-compose.yml` with Postgres, MinIO, Redpanda, Airflow
- `ingestion/sql/init/01_init_schemas.sql` — schemas and raw tables
- `ingestion/utils/pg_bootstrap.py` — idempotent applier of post-init SQL scripts
- `ingestion/utils/config.py` — typed singleton via `pydantic-settings`
- `ingestion/utils/pg_client.py` — psycopg2 wrapper with `transaction()` context manager

**Validation:** `docker compose ps` shows all services healthy; `pg_bootstrap` runs without error.

### Phase 2 — Streaming

**Goal:** capture Binance ticks at sub-second latency.

**Deliverables:**
- `ingestion/streaming/create_topics.py` — creates the `ticks` topic in Redpanda (idempotent)
- `ingestion/streaming/binance_producer.py` — WebSocket → Redpanda
- `ingestion/streaming/redpanda_consumer.py` — Redpanda → Postgres `raw.ticks`

**Validation:** after a few seconds, `SELECT COUNT(*) FROM raw.ticks` keeps growing. Useful command: `make stream-tail` or its psql equivalent.

### Phase 3 — Batch ingestion + bronze lakehouse

**Goal:** hourly/daily data from REST sources, materialized as Parquet in MinIO + `raw.*` tables in Postgres.

**Deliverables:**
- `ingestion/batch/coingecko_loader.py` — pulls market snapshots
- `ingestion/batch/reddit_loader.py` — top posts from crypto subreddits, with `mentions_btc/eth/...` flags
- `ingestion/batch/fng_loader.py` — Fear & Greed Index
- `ingestion/utils/minio_client.py` — boto3 wrapper

**Validation:** `.parquet` files appear in `bronze/...` buckets (MinIO Console); `raw.coingecko_markets`, `raw.reddit_posts`, `raw.fear_greed_index` populated.

### Phase 4 — dbt staging + marts

**Goal:** classic dimensional model on top of raw data.

**Deliverables:**
- `dbt_project/models/staging/*.sql` — 6 staging models (one per source)
- `dbt_project/models/marts/core/` — `dim_coin`, `dim_date`, `fact_prices_hourly`, `fact_market_snapshot`, `fact_sentiment_daily`
- `dbt_project/models/marts/analytics/` — `mart_top_movers_daily`, `mart_social_vs_price`
- `dbt_project/models/*.yml` — tests (`unique`, `not_null`, `accepted_values`, `relationships`)

**Validation:** `dbt run` creates the tables in `analytics_marts.*`; `dbt test` passes everything.

### Phase 5 — Machine Learning

**Goal:** turn raw data into actionable signals.

**Deliverables:**
- `ml/sentiment/vader_scorer.py` — runs VADER on `raw.reddit_posts.text`, writes to `ml.reddit_sentiment` (compound, sentiment_label)
- `ml/anomaly/price_anomalies.py` — over `fact_prices_hourly`:
  - rolling 168h z-score
  - IsolationForest contamination=0.05
  - `is_anomaly_consensus` flag when both agree
- `ingestion/sql/init/03_ml_tables.sql` — `ml.reddit_sentiment`, `ml.price_anomalies` tables
- `mart_anomaly_alerts.sql` (analytics) — joins anomalies with market and sentiment context

**Validation:** `SELECT COUNT(*) FROM ml.price_anomalies WHERE is_anomaly_consensus` returns > 0 (after several hours of data).

### Phase 6 — Airflow

**Goal:** orchestrate everything above without manual scripts.

**Deliverables:**
- `airflow/dags/cryptopulse_hourly.py` — TaskGroups: ingest → transform → ml → validate → data_quality → notify
- `airflow/dags/cryptopulse_daily.py` — VADER (more expensive)
- `airflow/dags/cryptopulse_streaming_health.py` — sensor that fails if `raw.ticks` has not received data in X minutes
- `airflow/plugins/cryptopulse_common/` — `python_module_task` and `dbt_task` helpers to avoid boilerplate

**Validation:** manual trigger of the hourly DAG from the UI or `airflow dags trigger`.

### Phase 7 — Data Quality (Great Expectations)

**Goal:** ensure data meets business invariants.

**Deliverables:**
- `quality/suites.py` — defines suites:
  - `raw_ticks_suite` — price > 0, symbol in WHITELIST_BINANCE
  - `mart_anomaly_alerts_suite` — `severity_score >= 0`, critical columns not null
  - cross-column: `expect_column_pair_values_a_to_be_greater_than_b` (high vs low)
- `quality/run_checkpoint.py` — runner that loads the context, runs the chosen suites, and emits results to `quality/results/`

**Notes:** GE 0.18 (not 1.x). Use `add_or_update_expectation_suite()`. There are deliberately two symbol whitelists (Binance vs base).

**Validation:** `python -m quality.run_checkpoint` prints summary and exits 0 if all passed.

### Phase 8 — Power BI

**Goal:** non-technical executive dashboard.

**Deliverables:**
- `ingestion/sql/init/04_bi_views.sql` — 5 stable views (`bi.v_kpi_latest`, `bi.v_price_hourly`, `bi.v_anomaly_alerts`, `bi.v_sentiment_daily`, `bi.v_market_snapshot_latest`)
- `dashboard/powerbi/queries.m` — 6 Power Query (M) snippets
- `dashboard/powerbi/measures.dax` — 39 DAX measures
- `dashboard/powerbi/layout_spec.md` — paint-by-numbers for the 4 pages
- `dashboard/powerbi/README.md` — assembly guide

**Dashboard pages:**
1. Executive Summary (KPI cards + normalized line + alerts bar + top movers)
2. Price Anomalies (line with markers + log table + donut by detector)
3. Sentiment Tracker (Fear&Greed + VADER + Reddit posts/day)
4. Market Overview (CoinGecko-style table + market share bar + KPIs)

**Validation:** `Home → Refresh` in Power BI Desktop without error; KPI cards show numbers (not Blank).

### Phase 9 — Streamlit Lab

**Goal:** interactive web app complementary to the PBI, with an AI agent.

**Deliverables:**
- `dashboard/streamlit_app.py` — home with sidebar that verifies Postgres and the LLM API key
- `dashboard/pages/01_Live_Tick_Tail.py` — auto-refresh every N seconds of the `raw.ticks` tail; per-symbol traffic light (green <5 min, yellow <15 min, red ≥15 min)
- `dashboard/pages/02_Alert_Explainer.py` — alert selector + mini price-context chart + "Explain with AI" button
- `dashboard/lib/db.py` — wrappers with `st.cache_resource` (PgClient singleton) and `st.cache_data(ttl=...)` per query, with automatic recovery from `transaction aborted`
- `dashboard/lib/llm.py` — Anthropic client + structured prompt builder

**Prompt design:** system = "you are a quantitative crypto analyst"; user = markdown table with metadata + hourly price window. Model returns markdown with fixed sections: Verdict / Signals / Context / Hypotheses / What to watch.

**Validation:** `streamlit run dashboard/streamlit_app.py`, navigate between pages, click "Explain" → Claude response on screen.

### Phase 10 — Telegram + CI/CD

**Goal:** push alerts + repo quality gating on every PR.

**Deliverables:**
- `alerts/telegram_notifier.py` — reads `bi.v_anomaly_alerts`, dedupes against `alerts.telegram_sent`, HTTP POST to the Bot API
- `ingestion/sql/init/05_alerts_tables.sql` — `alerts` schema + dedup table with `alert_key` PRIMARY KEY
- Hourly DAG: new `notify` TaskGroup with `notify_telegram` after `data_quality`
- `.github/workflows/ci.yml` — installs Python + deps, runs `ruff check` + `pytest -m "not integration"`

**Message design:** HTML parse-mode, basic section (symbol, hour, price, return, z-score, severity, F&G, Reddit, VADER) + optional LLM-generated block (if `ANTHROPIC_API_KEY` is set).

**Validation:** smoke test `python -c "..."`; over hours the DAG fires real messages.

### Phase 11 — Documentation + e2e

**Goal:** close the deliverable.

**Deliverables:**
- `README.md` rewritten (overview, badges, quickstart, phases)
- `docs/RUNBOOK.md` — operational runbook + 11 resolved gotchas
- `docs/COMPLETE_GUIDE.md` — this document
- `docs/screenshots/` — guide of the captures still pending upload

**Validation:** run the e2e checklist in `RUNBOOK.md`: 15 green items.

---

## 7. Key functions and modules

A quick guide for someone opening the repo for the first time. In order of importance.

### `ingestion/utils/config.py` — the single source of truth for configuration

All code imports `from ingestion.utils.config import settings`. It is a `pydantic-settings` object that reads `.env` ONCE, caches with `lru_cache`, and exposes typed properties. If you add a variable, add it to the `Settings` class.

### `ingestion/utils/pg_client.py` — thin layer over psycopg2

`PgClient` with `.conn` (lazy connect), `.transaction()` (context manager with auto commit/rollback), `.execute_script()` (SQL from file), `.upsert_dataframe()` (batch via `execute_values`). The rest of the code accesses Postgres through this client.

### `ingestion/utils/pg_bootstrap.py` — idempotent applier

Walks `ingestion/sql/init/*.sql` in alphabetical order and runs them via psycopg2. `01_init_schemas.sql` is in `SKIP_BY_DEFAULT` because it uses psql meta-commands (the container runs it in its init). Accepts `--only <file>` and `--force-all`.

### `ml/anomaly/price_anomalies.py` — the heart of Phase 5

Loads `analytics_marts.fact_prices_hourly`, computes rolling z-score and trains IsolationForest, writes to `ml.price_anomalies` with per-detector flags + `is_anomaly_consensus`. That consensus flag is what eventually triggers Telegram.

### `dashboard/lib/db.py` — Streamlit ↔ Postgres bridge

Decorates the client with `@st.cache_resource` and each query with `@st.cache_data(ttl=...)`. Implements `_safe_reset()` to recover from `transaction aborted` that happens when a query fails and leaves the connection in a broken state.

### `dashboard/lib/llm.py` — Alert Explainer agent

Singleton of the Anthropic client with `@st.cache_resource`. The central function `build_user_prompt(ctx)` takes an alert + price window and produces a rich prompt. `explain_alert(ctx)` sends and returns markdown ready for `st.markdown()`. Gracefully handles missing API key or package.

### `alerts/telegram_notifier.py` — from DB to Telegram

`fetch_pending_alerts()` with dedup via LEFT JOIN against `alerts.telegram_sent`. `build_basic_message()` formats HTML. `maybe_add_llm_summary()` enriches if there is a key. `mark_sent()` records (idempotent with `ON CONFLICT DO NOTHING`).

### `airflow/dags/cryptopulse_hourly.py` — the orchestra conductor

DAG with cron `15 * * * *` (every hour at minute 15). 6 chained TaskGroups. Uses the plugin's `python_module_task` and `dbt_task` helpers to avoid repeating `cwd`/`env` in each task.

---

## 8. Day-to-day operations

### 8.1. Frequent commands cheat sheet

```powershell
# Stack health
docker compose ps

# View recent ticks
docker compose exec postgres psql -U cryptopulse -d cryptopulse -c \
  "SELECT symbol, MAX(event_time) FROM raw.ticks GROUP BY 1 ORDER BY 2 DESC;"

# Manually refresh all silver+gold
python -m ingestion.batch.coingecko_loader ; python -m ingestion.batch.fng_loader
cd dbt_project ; dbt run ; dbt test ; cd ..

# Re-apply BI views (if Power BI throws "key didn't match")
python -m ingestion.utils.pg_bootstrap --only 04_bi_views.sql

# Trigger Airflow manually
docker compose exec airflow-scheduler airflow dags trigger cryptopulse_hourly

# Send pending alerts
python -m alerts.telegram_notifier --lookback-hours 24 --min-severity 1

# Telegram debug mode (sends nothing, only logs)
python -m alerts.telegram_notifier --dry-run --lookback-hours 24 --min-severity 0
```

### 8.2. How to add a new symbol

1. Edit `.env` → `TRACKED_SYMBOLS=BTCUSDT,ETHUSDT,...,NEWUSDT`
2. Edit `ingestion/utils/config.py` → property `coingecko_ids` (mapping `BTCUSDT → bitcoin`, etc.) — add the new one
3. Restart the producer: `Ctrl+C` in the `binance_producer` terminal and relaunch
4. Wait for the next hourly DAG run (or trigger manually)
5. Verify `dim_coin` includes it after the next `dbt run`

### 8.3. How to add a new BI view

1. Add `CREATE OR REPLACE VIEW bi.v_new AS …` at the end of `04_bi_views.sql`
2. `python -m ingestion.utils.pg_bootstrap --only 04_bi_views.sql`
3. In Power BI: `Home → Transform data → New Source → PostgreSQL → bi.v_new`
4. Rename the query and load
5. If it introduces new dimensions, create the relationships in Model view

### 8.4. How to shut down and restart

```powershell
# Shut down (data persists in data/postgres and data/minio)
docker compose down

# Shut down AND wipe data (careful)
docker compose down -v
Remove-Item data/postgres/* -Recurse
Remove-Item data/minio/* -Recurse

# Restart
docker compose up -d
python -m ingestion.utils.pg_bootstrap   # re-apply post-init scripts
```

---

## 9. Troubleshooting

> For the exhaustive list with causes and solutions, see [`RUNBOOK.md` section 6](RUNBOOK.md#6-gotchas--fixes). Here is the condensed version.

| Symptom | Likely cause | Quick fix |
|---|---|---|
| `relation "bi.v_*" does not exist` | BI views were not created or got dropped | `python -m ingestion.utils.pg_bootstrap --only 04_bi_views.sql` |
| Power BI: "key didn't match any rows" | Schema cache in PBI | Data source settings → Clear Permissions → reconnect |
| Streamlit: "current transaction is aborted" | psycopg2 connection in broken state | Already patched in `dashboard/lib/db.py` with `_safe_reset()` |
| `ModuleNotFoundError: dashboard` in Streamlit | sys.path missing the repo root | The shim is in `streamlit_app.py` and each page; ALWAYS run from the repo root |
| Telegram: "chat not found" | The user never sent `/start` to the bot | Find the bot in Telegram and send `/start` |
| `streamlit` not on PATH | venv didn't install the binary in `Scripts/` | `python -m streamlit run dashboard/streamlit_app.py` |
| `add_or_update_expectation_suite` AttributeError | Wrong GE version (1.x instead of 0.18) | `pip install great-expectations==0.18.15` |
| File with null bytes after Write | Incomplete Windows-Linux mount | Rewrite via bash or `path.write_bytes(p.read_bytes().rstrip(b'\x00'))` |

---

## 10. Glossary for non-technical readers

| Term | What it means in this project |
|---|---|
| **Tick** | An individual price observation received from Binance (there can be dozens per minute per symbol) |
| **Bronze / Silver / Gold** | Layers of the data lake. Bronze = raw, Silver = clean, Gold = report-ready |
| **Dimensional model** | A way to organize tables for analysis: facts (what happened) + dimensions (descriptive attributes) |
| **Fact / Dim** | "Fact" = table of numeric events; "Dim" = table of descriptive attributes |
| **Z-score** | How many standard deviations a return is from the historical mean |
| **Isolation Forest** | ML algorithm that isolates outliers by building random trees |
| **Consensus rule** | Marking something as anomalous only if two independent algorithms confirm it |
| **Idempotent** | An operation that yields the same result no matter how many times you run it |
| **DAG** | Directed Acyclic Graph — Airflow's task graph |
| **Multipage app (Streamlit)** | A Streamlit app with several pages auto-detected from a `pages/` folder |
| **Parse mode HTML** | The format Telegram uses for text with `<b>`, `<code>`, etc. |
| **Schema cache (PBI)** | Power BI caches Postgres' schema list the first time it connects — afterwards it doesn't notice new schemas until you clear permissions |

---

## 11. Next improvements

Concrete ideas to extend the project, ordered by impact/effort.

### Short (1-3 hours)

- **`bi.v_coin_performance_30d`** — comparative view of 1d/7d/30d returns.
- **Power BI visual theme** — `theme.json` with a consistent palette.
- **Integration test** — test that boots Postgres with docker, runs `pg_bootstrap`, validates the schemas created.

### Medium (1-2 days)

- **Simple backtest** in Streamlit: long on negative consensus, hold N hours, compute Sharpe.
- **Drill-through in Power BI** — from alert → detail page filtered by `symbol + time range`.
- **dbt exposures** — declare the PBI/Streamlit apps as downstream consumers in dbt's graph.
- **Alembic / dbt-snapshot** on `dim_coin` for SCD type 2 when attributes change.

### Long (1+ week)

- **Cloud deployment** — Terraform for AWS (RDS + S3 + MWAA) or GCP equivalent.
- **React/Next.js frontend** replacing Streamlit for a more polished experience.
- **Forecasting models** — Prophet / Chronos for short-term prediction, comparable against actual returns.
- **Feature store** — turn `mart_anomaly_alerts` into a reusable feature set with Feast or similar.

---

> **Author:** Frago — `jeanpaulmayers@outlook.es`
>
> This project is a portfolio. Any feedback, issue, or PR is welcome.
