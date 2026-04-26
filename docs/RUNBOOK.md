# CryptoPulse — Runbook

Operational guide. Use this when bringing the stack up from zero, debugging, or onboarding.

---

## 1. Bootstrap from a cold checkout

Pre-requisites: Docker Desktop, Python 3.11, PowerShell (or any shell), Git.

```powershell
git clone <repo> ; cd cryptopulse
cp .env.example .env
# Edit .env:
#   POSTGRES_PASSWORD       (required)
#   REDDIT_CLIENT_ID/SECRET (Phase 3)
#   ANTHROPIC_API_KEY       (Phase 9 LLM)
#   ANTHROPIC_MODEL=claude-haiku-4-5-20251001
#   TELEGRAM_BOT_TOKEN      (Phase 10)
#   TELEGRAM_CHAT_ID        (Phase 10)

python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
docker compose up -d                                # postgres, minio, redpanda, airflow
python -m ingestion.utils.pg_bootstrap              # applies 02_… 03_… 04_… 05_…
```

Sanity check Postgres:

```powershell
docker compose exec postgres psql -U cryptopulse -d cryptopulse -c "\dn"
# expected schemas: alerts, analytics_marts, bi, ml, public, raw
```

---

## 2. Run the pipeline once

```powershell
# (Optional) start the streaming producer in a separate terminal
python -m ingestion.streaming.create_topics
python -m ingestion.streaming.binance_producer    # leave running
python -m ingestion.streaming.redpanda_consumer   # leave running

# Batch ingestion
python -m ingestion.batch.coingecko_loader
python -m ingestion.batch.reddit_loader
python -m ingestion.batch.fng_loader

# Transform
cd dbt_project
dbt deps
dbt run
dbt test
cd ..

# ML
python -m ml.sentiment.vader_scorer
python -m ml.anomaly.price_anomalies
cd dbt_project ; dbt run --select mart_anomaly_alerts ; cd ..

# Quality
python -m quality.run_checkpoint

# Refresh BI views
python -m ingestion.utils.pg_bootstrap --only 04_bi_views.sql
```

---

## 3. Spin up Airflow (orchestrated mode)

```powershell
docker compose up -d airflow-init airflow-webserver airflow-scheduler
# UI: http://localhost:8081  (admin / admin)
docker compose exec airflow-scheduler airflow dags list
docker compose exec airflow-scheduler airflow dags trigger cryptopulse_hourly
```

The hourly DAG covers ingest → transform → ML → dbt test → GE → Telegram notify.
Daily DAG handles VADER. Streaming health DAG probes `raw.ticks` freshness.

---

## 4. Dashboards

### Power BI (Phase 8)

```powershell
# Make sure bi.* views exist
python -m ingestion.utils.pg_bootstrap --only 04_bi_views.sql
# Verify
docker compose exec postgres psql -U cryptopulse -d cryptopulse -c "SELECT viewname FROM pg_views WHERE schemaname='bi';"
```

Then open Power BI Desktop, follow [`dashboard/powerbi/README.md`](../dashboard/powerbi/README.md). The `.pbix` is gitignored; commit `.pbit` only if sharing.

### Streamlit Lab (Phase 9)

```powershell
streamlit run dashboard/streamlit_app.py
# http://localhost:8501
```

Two pages: Live Tick Tail (auto-refresh tail of `raw.ticks` with per-symbol freshness traffic light) and Alert Explainer (Claude-powered analysis of any row in `bi.v_anomaly_alerts`).

### Telegram (Phase 10)

```powershell
# Bootstrap dedup table once
python -m ingestion.utils.pg_bootstrap --only 05_alerts_tables.sql

# Quick smoke test (no DB lookup)
python -c "from alerts.telegram_notifier import send_to_telegram; print(send_to_telegram('<b>Test</b>', dry_run=False))"

# Real run (only sends new consensus alerts in last 6h, severity >= 3)
python -m alerts.telegram_notifier
```

In Airflow, this is the `notify.notify_telegram` task at the end of `cryptopulse_hourly`. It is idempotent thanks to `alerts.telegram_sent`.

---

## 5. End-to-end validation checklist

Run this after a clean bootstrap:

- [ ] `docker compose ps` — all services healthy
- [ ] `pg_bootstrap` applied 02_, 03_, 04_, 05_ scripts without error
- [ ] `raw.ticks` has rows growing (run `make stream-tail`)
- [ ] `raw.coingecko_markets`, `raw.reddit_posts`, `raw.fear_greed_index` populated
- [ ] `dbt run` passes — staging + marts materialized
- [ ] `dbt test` passes — schema + business tests green
- [ ] `ml.reddit_sentiment` populated (VADER)
- [ ] `ml.price_anomalies` populated (z-score + IForest)
- [ ] `analytics_marts.mart_anomaly_alerts` populated
- [ ] `bi.v_*` returns rows for `v_kpi_latest`, `v_price_hourly`, `v_sentiment_daily`, `v_market_snapshot_latest`
- [ ] Power BI refresh succeeds, all 4 pages render KPI cards
- [ ] Streamlit Live Tick Tail shows green traffic lights
- [ ] Streamlit Alert Explainer returns a Claude-generated paragraph
- [ ] Telegram smoke test arrives in the chat
- [ ] GitHub Actions CI run is green on `main`

---

## 6. Gotchas & fixes

A flat list of every issue we hit during the build, with the actual fix.

### `01_init_schemas.sql` is skipped by `pg_bootstrap`
**Why:** that script uses psql meta-commands (`\c`, etc.) and is run by the Postgres container's `docker-entrypoint-initdb.d` exactly once. `pg_bootstrap` (psycopg2) cannot run psql meta-commands.
**Fix:** if you nuke volumes (`make clean`), let the container's init handle 01 again. `pg_bootstrap` only handles 02 onwards (`SKIP_BY_DEFAULT` set in `ingestion/utils/pg_bootstrap.py`).

### `bi.*` views "disappear" between sessions
**Symptom:** `psycopg2.errors.UndefinedTable: relation "bi.v_anomaly_alerts" does not exist` even though we ran `04_bi_views.sql` earlier.
**Cause:** any operation that recreates the schema — `make clean`, `docker compose down -v`, or specific dbt configurations — can wipe non-dbt-managed objects.
**Fix:** make `make bi-views` part of your post-deploy checklist. The Streamlit Lab and Power BI both depend on these views.
```powershell
python -m ingestion.utils.pg_bootstrap --only 04_bi_views.sql
```

### Power BI Navigator does not show the `bi` schema
**Cause:** Power BI caches the schema list per data source. If you opened PBI before applying `04_bi_views.sql`, the cache is stale.
**Fix:**
1. `Home → Transform data → Data source settings → localhost:5432;cryptopulse → Clear Permissions` (do this for both `localhost:5432` and `localhost:5432;cryptopulse`).
2. Close PBI completely.
3. Reopen → `Get Data → PostgreSQL` → reconnect.

### Power BI: "key didn't match any rows" on refresh
**Cause:** the M query references a schema/table that does not exist right now. Usually `bi.*` views were dropped (see above).
**Fix:** re-apply `04_bi_views.sql`, then `Home → Refresh` in PBI.

### Power BI: cannot relate `datetimezone` to `date` column
**Cause:** PBI rejects relationships across `datetimezone` ↔ `date`.
**Fix:** add a calculated column on the fact:
```dax
date = DATE(YEAR([ts_hour]), MONTH([ts_hour]), DAY([ts_hour]))
```
Use this `date` column in the relationship to `DateDim[date]`.

### Great Expectations 0.18 vs 1.x API
**Symptom:** `AttributeError: 'AbstractDataContext' object has no attribute 'add_or_update_expectation_suite'` (or similar).
**Cause:** GE 0.18 ≠ GE 1.x. We pinned 0.18 (see `requirements.txt`).
**Notes used in this codebase:**
- Use `add_or_update_expectation_suite()` (0.18 method).
- For `expect_column_pair_values_a_to_be_greater_than_b` use **lowercase** function name but the kwargs are **`column_A`** / **`column_B`** with capitals — not `column_a`/`column_b`.

### Two whitelists of symbols (Binance vs CoinGecko)
**Why:** Binance uses `BTCUSDT`/`ETHUSDT`/…, CoinGecko uses base symbols `BTC`/`ETH`/…
**Where:** `quality/suites.py` carries both whitelists. Don't unify them — they are intentionally separate.

### Streamlit: `current transaction is aborted, commands ignored`
**Cause:** the singleton `PgClient` carries a cross-page connection. If a query failed in one page, the connection is left in aborted state and the next query in another page fails with this error until you `ROLLBACK`.
**Fix:** `dashboard/lib/db.py:fetch_df` wraps every query in `pg.transaction()` which commits on success and rolls back on error. There is also a `_safe_reset()` that is invoked on exception to recover.

### Streamlit: `ModuleNotFoundError: No module named 'dashboard'`
**Cause:** Streamlit only adds the dir of the entry script to `sys.path`, not the repo root.
**Fix:** `dashboard/streamlit_app.py` and each page in `dashboard/pages/` start with a `sys.path.insert(0, REPO_ROOT)` shim.

### Telegram: `Bad Request: chat not found`
**Cause:** Telegram blocks bots from messaging users who never started the bot.
**Fix:** open Telegram, search for *your bot*'s name, send `/start`. Then retry.

### Windows-Linux mount: files written with trailing null bytes
**Symptom:** `ValueError: source code string cannot contain null bytes` when parsing a Python file just written through the Cowork file tools.
**Cause:** the mount layer between the Windows filesystem and the sandbox sometimes preserves the previous file's tail when overwriting with shorter content.
**Fix:** rewrite the file via bash (`cat > path << EOF … EOF`) or strip trailing nulls:
```python
p = Path('file.py'); p.write_bytes(p.read_bytes().rstrip(b'\\x00'))
```

### `streamlit` not on PATH inside venv
**Symptom:** `'streamlit' is not recognized…` in PowerShell.
**Fix:** invoke as a module instead:
```powershell
python -m streamlit run dashboard/streamlit_app.py
```

---

## 7. Cheat sheet

```powershell
# Fresh DB / pipeline run
python -m ingestion.utils.pg_bootstrap
python -m ingestion.batch.coingecko_loader
python -m ingestion.batch.reddit_loader
python -m ingestion.batch.fng_loader
cd dbt_project ; dbt run ; dbt test ; cd ..
python -m ml.sentiment.vader_scorer
python -m ml.anomaly.price_anomalies
cd dbt_project ; dbt run --select mart_anomaly_alerts ; cd ..

# Refresh BI views (do this before opening Power BI)
python -m ingestion.utils.pg_bootstrap --only 04_bi_views.sql

# Streamlit
python -m streamlit run dashboard/streamlit_app.py

# Telegram (real)
python -m alerts.telegram_notifier

# Airflow trigger
docker compose exec airflow-scheduler airflow dags trigger cryptopulse_hourly
```
