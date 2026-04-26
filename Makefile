# =============================================================================
# CryptoPulse — Comandos útiles
# Uso: make <target>   (en Windows: usar Git Bash o WSL)
# =============================================================================

.PHONY: help up down restart logs ps clean psql minio redpanda airflow \
        stream-producer stream-consumer batch-run dbt-run dbt-test \
        ml-bootstrap ml-sentiment ml-anomalies ml-all gold-ml-e2e \
        airflow-up airflow-logs airflow-restart airflow-dags \
        airflow-trigger-hourly airflow-trigger-daily airflow-test-health \
        streamlit install lint format test pg-bootstrap dbt-deps dbt-debug \
        dbt-seed dbt-compile dbt-source-freshness silver-e2e \
        ge-run ge-run-suite ge-clean bi-views bi-check \
        alerts-bootstrap telegram-dry-run telegram-send

help: ## Lista todos los comandos disponibles
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ---------- Infraestructura ----------
up: ## Levanta todos los servicios (postgres, minio, redpanda, airflow)
	docker compose up -d
	@echo ""
	@echo "Servicios corriendo:"
	@echo "  Postgres        -> localhost:5432"
	@echo "  MinIO API       -> http://localhost:9000"
	@echo "  MinIO Console   -> http://localhost:9001  (user: minio / pass: ver .env)"
	@echo "  Redpanda        -> localhost:9092"
	@echo "  Redpanda UI     -> http://localhost:8080"
	@echo "  Airflow         -> http://localhost:8081   (admin / admin)"

down: ## Para todos los servicios
	docker compose down

restart: down up ## Reinicia todo

logs: ## Sigue los logs de todos los servicios
	docker compose logs -f --tail=100

ps: ## Lista servicios y su estado
	docker compose ps

clean: ## ¡CUIDADO! Borra volúmenes y datos locales
	docker compose down -v
	rm -rf data/postgres/* data/minio/* airflow/logs/*

# ---------- Accesos rápidos ----------
psql: ## Abre shell de psql en el contenedor
	docker compose exec postgres psql -U cryptopulse -d cryptopulse

redpanda-topics: ## Lista topics de Redpanda
	docker compose exec redpanda rpk topic list

# ---------- Ingestión ----------
create-topics: ## Crea los topics en Redpanda (idempotente)
	python -m ingestion.streaming.create_topics

stream-producer: ## Arranca el producer de Binance WS → Redpanda
	python -m ingestion.streaming.binance_producer

stream-consumer: ## Arranca el consumer de Redpanda → Postgres
	python -m ingestion.streaming.redpanda_consumer

stream-tail: ## Ver ticks recién llegados a Postgres (last 20)
	docker compose exec postgres psql -U cryptopulse -d cryptopulse -c \
	  "SELECT symbol, event_time, price, volume_base FROM raw.ticks ORDER BY event_time DESC LIMIT 20;"

stream-count: ## Contar filas por símbolo en raw.ticks
	docker compose exec postgres psql -U cryptopulse -d cryptopulse -c \
	  "SELECT symbol, COUNT(*) AS ticks, MAX(event_time) AS last_seen FROM raw.ticks GROUP BY symbol ORDER BY ticks DESC;"

batch-run: ## Ejecuta todos los loaders batch (MinIO + Postgres dual-write)
	python -m ingestion.batch.coingecko_loader
	python -m ingestion.batch.reddit_loader
	python -m ingestion.batch.fng_loader

pg-bootstrap: ## Aplica los .sql de ingestion/sql/init/ (idempotente)
	python -m ingestion.utils.pg_bootstrap

# ---------- dbt ----------
dbt-deps: ## Instala packages de dbt (dbt_utils, dbt_date)
	cd dbt_project && DBT_PROFILES_DIR=. dbt deps

dbt-debug: ## Verifica conexión y configuración de dbt
	cd dbt_project && DBT_PROFILES_DIR=. dbt debug

dbt-seed: ## Carga seeds estáticos (mapping de símbolos, etc.)
	cd dbt_project && DBT_PROFILES_DIR=. dbt seed

dbt-compile: ## Compila los modelos sin ejecutarlos
	cd dbt_project && DBT_PROFILES_DIR=. dbt compile

dbt-run: ## Corre todos los modelos dbt (staging + marts)
	cd dbt_project && DBT_PROFILES_DIR=. dbt run

dbt-test: ## Corre los tests de dbt (schema + datos)
	cd dbt_project && DBT_PROFILES_DIR=. dbt test

dbt-source-freshness: ## Chequea frescura de sources (raw.*)
	cd dbt_project && DBT_PROFILES_DIR=. dbt source freshness

dbt-docs: ## Genera y sirve la documentación de dbt
	cd dbt_project && DBT_PROFILES_DIR=. dbt docs generate && DBT_PROFILES_DIR=. dbt docs serve

silver-e2e: pg-bootstrap batch-run dbt-deps dbt-run dbt-test ## Pipeline silver completo de cero

# ---------- ML (Fase 5) ----------
ml-bootstrap: ## Crea las tablas del schema ml (idempotente)
	python -m ingestion.utils.pg_bootstrap --only 03_ml_tables.sql

ml-sentiment: ## VADER sentiment scoring sobre posts de Reddit
	python -m ml.sentiment.vader_scorer

ml-anomalies: ## Detecta anomalías en fact_prices_hourly (z-score + IsolationForest)
	python -m ml.anomaly.price_anomalies

ml-all: ml-bootstrap ml-sentiment ml-anomalies ## Corre la Fase 5 completa
	@echo "ML jobs listos. Ahora corre: make dbt-run && make dbt-test"

gold-ml-e2e: ml-all dbt-run dbt-test ## Pipeline ML + refresh de marts de punta a punta

# ---------- Airflow (Fase 6) ----------
airflow-up: ## Arranca solo los servicios de Airflow
	docker compose up -d airflow-init airflow-webserver airflow-scheduler
	@echo "Airflow UI: http://localhost:8081   (admin/admin)"

airflow-logs: ## Sigue logs del scheduler + webserver
	docker compose logs -f airflow-scheduler airflow-webserver

airflow-restart: ## Reinicia el scheduler (recarga DAGs rápido)
	docker compose restart airflow-scheduler

airflow-dags: ## Lista DAGs cargados en el scheduler
	docker compose exec airflow-scheduler airflow dags list

airflow-trigger-hourly: ## Dispara manualmente el DAG horario
	docker compose exec airflow-scheduler airflow dags trigger cryptopulse_hourly

airflow-trigger-daily: ## Dispara manualmente el DAG diario
	docker compose exec airflow-scheduler airflow dags trigger cryptopulse_daily

airflow-test-health: ## Testea el DAG de streaming_health sin schedule
	docker compose exec airflow-scheduler airflow tasks test \
	  cryptopulse_streaming_health check_tick_freshness 2026-01-01

# ---------- Data Quality (Fase 7) ----------
ge-run: ## Corre todas las suites de Great Expectations contra Postgres
	python -m quality.run_checkpoint

ge-run-suite: ## Corre UNA suite de GE (uso: make ge-run-suite SUITE=raw_ticks)
	python -m quality.run_checkpoint --suite $(SUITE)

ge-clean: ## Borra resultados viejos de GE (quality/results/)
	rm -rf quality/results/*

# ---------- Dashboards ----------
bi-views: ## Aplica schema bi.* (vistas para Power BI) via pg_bootstrap
	python -m ingestion.utils.pg_bootstrap --only 04_bi_views.sql

bi-check: ## Verifica que las vistas bi.* existan y devuelvan filas
	docker compose exec postgres psql -U cryptopulse -d cryptopulse -c \
	  "SELECT table_name FROM information_schema.views WHERE table_schema='bi' ORDER BY 1;"
	docker compose exec postgres psql -U cryptopulse -d cryptopulse -c \
	  "SELECT 'v_kpi_latest' AS view, COUNT(*) AS rows FROM bi.v_kpi_latest UNION ALL \
	   SELECT 'v_price_hourly',       COUNT(*) FROM bi.v_price_hourly UNION ALL \
	   SELECT 'v_anomaly_alerts',     COUNT(*) FROM bi.v_anomaly_alerts UNION ALL \
	   SELECT 'v_sentiment_daily',    COUNT(*) FROM bi.v_sentiment_daily UNION ALL \
	   SELECT 'v_market_snapshot_latest', COUNT(*) FROM bi.v_market_snapshot_latest;"

streamlit: ## Arranca la app de Streamlit local
	streamlit run dashboard/streamlit_app.py

# ---------- Alertas (Fase 10) ----------
alerts-bootstrap: ## Crea schema alerts y la tabla telegram_sent
	python -m ingestion.utils.pg_bootstrap --only 05_alerts_tables.sql

telegram-dry-run: ## Simula envio sin pegarle a Telegram (para debug)
	python -m alerts.telegram_notifier --dry-run --lookback-hours 24 --min-severity 0

telegram-send: ## Manda alertas pendientes (severity >= 3, ultimas 6h)
	python -m alerts.telegram_notifier --min-severity 3 --lookback-hours 6

# ---------- Desarrollo ----------
install: ## Crea venv e instala dependencias
	python -m venv .venv
	./.venv/bin/pip install -U pip
	./.venv/bin/pip install -r requirements.txt

lint: ## Lint con ruff
	ruff check .

format: ## Formatea con ruff + black
	ruff check --fix .
	black .

test: ## Ejecuta tests unitarios
	pytest -v tests/
