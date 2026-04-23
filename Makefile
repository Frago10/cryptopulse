# =============================================================================
# CryptoPulse — Comandos útiles
# Uso: make <target>   (en Windows: usar Git Bash o WSL)
# =============================================================================

.PHONY: help up down restart logs ps clean psql minio redpanda airflow \
        stream-producer stream-consumer batch-run dbt-run dbt-test ml-train \
        streamlit install lint format test

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
stream-producer: ## Arranca el producer de Binance WS → Redpanda
	python -m ingestion.streaming.binance_producer

stream-consumer: ## Arranca el consumer de Redpanda → Postgres
	python -m ingestion.streaming.redpanda_consumer

batch-run: ## Ejecuta todos los loaders batch
	python -m ingestion.batch.coingecko_loader
	python -m ingestion.batch.reddit_loader
	python -m ingestion.batch.fng_loader

# ---------- dbt ----------
dbt-deps: ## Instala packages de dbt
	cd dbt_project && dbt deps

dbt-run: ## Corre todos los modelos dbt
	cd dbt_project && dbt run

dbt-test: ## Corre los tests de dbt
	cd dbt_project && dbt test

dbt-docs: ## Genera y sirve la documentación de dbt
	cd dbt_project && dbt docs generate && dbt docs serve

# ---------- ML ----------
ml-train: ## Entrena los modelos de anomalías y sentimiento
	python -m ml.train

# ---------- Dashboards ----------
streamlit: ## Arranca la app de Streamlit local
	streamlit run dashboard/streamlit_app.py

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
