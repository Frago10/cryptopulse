# CryptoPulse — Guía Completa

> Manual profesional del proyecto. Diseñado para que tanto un revisor técnico como alguien sin background de data engineering pueda entender qué hace el sistema, por qué está construido así, y cómo operarlo paso a paso.

---

## Índice

1. [Resumen ejecutivo](#1-resumen-ejecutivo)
2. [¿Qué problema resuelve?](#2-qué-problema-resuelve)
3. [Stack tecnológico explicado](#3-stack-tecnológico-explicado)
4. [Arquitectura de alto nivel](#4-arquitectura-de-alto-nivel)
5. [Setup paso a paso desde cero](#5-setup-paso-a-paso-desde-cero)
6. [Recorrido por las 11 fases](#6-recorrido-por-las-11-fases)
7. [Funciones y módulos clave](#7-funciones-y-módulos-clave)
8. [Operación día a día](#8-operación-día-a-día)
9. [Troubleshooting](#9-troubleshooting)
10. [Glosario para no técnicos](#10-glosario-para-no-técnicos)
11. [Próximas mejoras](#11-próximas-mejoras)

---

## 1. Resumen ejecutivo

**CryptoPulse** es una plataforma end-to-end de inteligencia de mercado cripto. Captura precios en tiempo real de Binance, los enriquece cada hora con datos de CoinGecko, Reddit y el Fear & Greed Index, los limpia y modela con dbt, aplica machine learning para detectar movimientos anómalos y sentimiento social, y entrega todo a través de tres canales: un dashboard ejecutivo en Power BI, una app interactiva en Streamlit con un agente de IA que explica las alertas, y notificaciones automáticas por Telegram.

Está construido como un proyecto de portafolio que demuestra dominio de las disciplinas centrales del data engineering moderno: streaming, batch, lakehouse en arquitectura medallion (bronze / silver / gold), modelado dimensional, ML aplicado, orquestación, calidad de datos, BI, alertas, y CI/CD.

**En una frase:** clonar el repo, ejecutar `docker compose up`, y en menos de una hora tienes un pipeline de datos cripto operativo de punta a punta.

---

## 2. ¿Qué problema resuelve?

Imagina que eres un trader o un analista que necesita responder preguntas como:

- ¿Qué tan saludable está el mercado cripto en este momento?
- ¿Bitcoin tuvo un movimiento anómalo en la última hora? ¿Por qué?
- ¿El sentimiento de Reddit anticipa o sigue al precio?
- ¿Cuál fue el peor performer de las últimas 24h?

Hoy, esa información vive dispersa: precios en Binance, métricas en CoinGecko, sentimiento en Reddit, índices en sitios externos. Consolidarla manualmente es lento y propenso a errores.

**CryptoPulse** automatiza esa consolidación. Captura los datos, los unifica, los procesa con ML para resaltar lo importante, y los presenta de manera ejecutiva. Si pasa algo relevante (por ejemplo, una caída anómala detectada por dos algoritmos independientes), avisa por Telegram con explicación incluida — sin que tengas que estar mirando una pantalla.

Es la versión "personal mini-Bloomberg" para cripto, construida con herramientas open source y desplegable en un laptop.

---

## 3. Stack tecnológico explicado

Cada herramienta cumple un rol específico. Aquí va la justificación accesible y la alternativa que descartamos.

### Capa de ingestión

| Herramienta | Para qué la usamos | Alternativa que descartamos |
|---|---|---|
| **Binance WebSocket** | Streaming de precios tick-a-tick (sub-segundo) | Polling REST: latencia mucho mayor |
| **Redpanda** | Broker tipo Kafka para desacoplar producer y consumer | Kafka clásico: más pesado para correr en laptop |
| **Python `confluent-kafka`** | Cliente del broker, alto throughput | `kafka-python`: más lento |
| **`requests` / `praw`** | Llamadas REST a CoinGecko y Reddit | `aiohttp`: complejidad innecesaria para volumen bajo |
| **`pydantic-settings`** | Configuración tipada desde `.env` | `os.getenv` regado por todo el código |

### Capa de almacenamiento

| Herramienta | Para qué la usamos | Por qué |
|---|---|---|
| **MinIO** | Object store local compatible con S3 (capa bronze) | Mismo API que AWS S3 — el código sería idéntico en producción |
| **PostgreSQL 15** | Warehouse principal (silver + gold) | Soporta JSONB, particionamiento, ricos índices, plus dbt-postgres es maduro |
| **Parquet** | Formato columnar comprimido para data lake | Ahorra 5-10× espacio vs CSV, lectura selectiva por columna |

### Capa de transformación

| Herramienta | Rol |
|---|---|
| **dbt-postgres** | Define los modelos staging y marts en SQL versionado, con pruebas y documentación nativas |
| **dbt-utils, dbt-date** | Macros estándar (surrogate keys, tabla de fechas, etc.) |

### Machine Learning

| Herramienta | Para qué |
|---|---|
| **scikit-learn — IsolationForest** | Detección de anomalías sin etiquetas (unsupervised) |
| **Z-score rolling** | Detector estadístico clásico, complementa al IF |
| **Consensus rule** | Marca anomalía como "fuerte" solo si los DOS detectores la confirman → mejora la precisión, baja falsos positivos |
| **VADER sentiment** | Análisis lexicón rápido sobre posts de Reddit (devuelve compound score `[-1, +1]`) |

### Orquestación y calidad

| Herramienta | Para qué |
|---|---|
| **Apache Airflow 2.9** | DAGs declarativos: hourly (batch + ML + alertas), daily (VADER), streaming health probe |
| **Great Expectations 0.18** | Validaciones data quality declarativas: rangos, whitelists de símbolos, no-nulls |

### Visualización y comunicación

| Herramienta | Audiencia |
|---|---|
| **Power BI Desktop** | Stakeholders ejecutivos. Dashboard de 4 páginas con 39 medidas DAX |
| **Streamlit + Plotly** | Analistas técnicos. Interactivo, python-nativo, despliegue en 1 comando |
| **Telegram Bot API** | Mobile-first: notificaciones push donde estés |
| **Anthropic Claude (Haiku 4.5)** | Convierte una alerta cruda en una explicación en lenguaje natural |

### CI/CD

| Herramienta | Para qué |
|---|---|
| **Docker Compose** | Levanta todo el stack (Postgres, MinIO, Redpanda, Airflow) con un solo comando |
| **GitHub Actions** | Linter (ruff) + tests (pytest) en cada push y pull request |

---

## 4. Arquitectura de alto nivel

### 4.1. Diagrama de flujo de datos

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

### 4.2. Por qué medallion (bronze / silver / gold)

**Bronze** = datos crudos tal como llegaron, sin tocar. Vive en MinIO en Parquet (snapshots horarios) y en Postgres `raw.*` para acceso rápido. Si descubres un bug en una transformación río abajo, siempre puedes volver al bronze y reprocesar.

**Silver** = datos limpios y tipados, una fila por evento. Es donde dbt aplica deduplicación, casteos, normalización de símbolos. Las tablas `staging` viven aquí.

**Gold** = datos listos para análisis. Modelo dimensional clásico: facts (eventos numéricos) + dims (atributos). Esto es lo que un BI puede consumir directo.

**Capa BI (`bi.*` views)** = un escudo entre dbt y la herramienta de visualización. Si dbt renombra una columna de un mart, sólo actualizas la vista — el `.pbix` del analista no se rompe. Es el patrón "decoupling de presentación" aplicado a BI.

### 4.3. Streaming vs batch — por qué ambos

- **Streaming (Binance)**: precios cambian en milisegundos. Cualquier latencia es ruido. WebSocket + Redpanda + consumer Python lo resuelve.
- **Batch (CoinGecko, Reddit, F&G)**: market cap, supply, sentimiento — datos que cambian lento. Polling REST cada hora es suficiente y rate-limit friendly.

Mezclar las dos disciplinas en un mismo proyecto es exactamente lo que las plataformas reales hacen. No es streaming-puro ni batch-puro: es un hybrid pipeline.

---

## 5. Setup paso a paso desde cero

Asumimos Windows + PowerShell. Todo es válido para Linux/macOS cambiando rutas.

### 5.1. Pre-requisitos

| Software | Versión mínima | Cómo verificar |
|---|---|---|
| Docker Desktop | 4.20+ | `docker --version` |
| Python | 3.11 | `python --version` |
| Git | 2.40+ | `git --version` |
| Power BI Desktop | última | (opcional, sólo Fase 8) |

Cuentas opcionales (las dejas en blanco si no las usas, el sistema sigue corriendo):

- Reddit Dev App: https://www.reddit.com/prefs/apps (Phase 3)
- Anthropic API key: https://console.anthropic.com/settings/keys (Phase 9-10 LLM)
- Telegram bot token: chat con @BotFather (Phase 10)

### 5.2. Clonar y configurar entorno

```powershell
git clone <tu-repo> cryptopulse
cd cryptopulse

# Copia el template y edítalo con tus secretos
Copy-Item .env.example .env
notepad .env
```

Variables mínimas a setear en `.env`:

```ini
POSTGRES_PASSWORD=cryptopulse_local_2026
ANTHROPIC_API_KEY=sk-ant-...      # opcional Phase 9-10
ANTHROPIC_MODEL=claude-haiku-4-5-20251001
TELEGRAM_BOT_TOKEN=1234:ABC...    # opcional Phase 10
TELEGRAM_CHAT_ID=123456789        # opcional Phase 10
REDDIT_CLIENT_ID=...              # opcional, mejora datos sociales
REDDIT_CLIENT_SECRET=...
```

### 5.3. Ambiente Python

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 5.4. Levantar la infraestructura

```powershell
docker compose up -d
docker compose ps                  # todo Up (healthy)
```

Servicios disponibles después de `up`:

| Servicio | URL | Credenciales |
|---|---|---|
| Postgres | `localhost:5432` | `cryptopulse / <POSTGRES_PASSWORD>` |
| MinIO API | `http://localhost:9000` | `minio / minio12345` |
| MinIO Console | `http://localhost:9001` | mismas |
| Redpanda | `localhost:9092` | sin auth |
| Redpanda UI | `http://localhost:8080` | sin auth |
| Airflow UI | `http://localhost:8081` | `admin / admin` |

### 5.5. Bootstrap de la base de datos

```powershell
python -m ingestion.utils.pg_bootstrap
```

Esto aplica los scripts SQL en `ingestion/sql/init/` (excepto `01_init_schemas.sql`, que ya lo corrió Postgres en su entrypoint inicial).

### 5.6. Primer pipeline end-to-end

```powershell
# Ingestión batch (las APIs públicas no requieren key)
python -m ingestion.batch.coingecko_loader
python -m ingestion.batch.fng_loader
python -m ingestion.batch.reddit_loader   # requiere REDDIT_CLIENT_ID

# Transformación silver/gold
cd dbt_project
dbt deps
dbt run
dbt test
cd ..

# ML
python -m ml.sentiment.vader_scorer
python -m ml.anomaly.price_anomalies
cd dbt_project ; dbt run --select mart_anomaly_alerts ; cd ..

# Calidad de datos
python -m quality.run_checkpoint

# Vistas BI
python -m ingestion.utils.pg_bootstrap --only 04_bi_views.sql

# Streaming (en otra terminal, dejar corriendo)
python -m ingestion.streaming.create_topics
python -m ingestion.streaming.binance_producer
# en otra terminal:
python -m ingestion.streaming.redpanda_consumer
```

### 5.7. Lanzar las apps

```powershell
# Streamlit Lab
streamlit run dashboard/streamlit_app.py
# Abre http://localhost:8501

# Power BI: abre dashboard/powerbi/cryptopulse.pbix manualmente
# (sigue dashboard/powerbi/README.md la primera vez)

# Telegram smoke test
python -c "from alerts.telegram_notifier import send_to_telegram; print(send_to_telegram('<b>Test</b>', dry_run=False))"
```

---

## 6. Recorrido por las 11 fases

Cada fase es autocontenida. Construimos el proyecto fase por fase, validando cada una antes de avanzar — así el portafolio cuenta una historia y cada commit tiene sentido.

### Fase 1 — Infraestructura

**Objetivo:** levantar el stack base reproducible.

**Entregables:**
- `docker-compose.yml` con Postgres, MinIO, Redpanda, Airflow
- `ingestion/sql/init/01_init_schemas.sql` — schemas y tablas raw
- `ingestion/utils/pg_bootstrap.py` — aplicador idempotente de scripts SQL post-init
- `ingestion/utils/config.py` — singleton tipado con `pydantic-settings`
- `ingestion/utils/pg_client.py` — wrapper psycopg2 con `transaction()` context manager

**Validación:** `docker compose ps` muestra todos los servicios healthy, `pg_bootstrap` corre sin error.

### Fase 2 — Streaming

**Objetivo:** capturar ticks de Binance en sub-segundo.

**Entregables:**
- `ingestion/streaming/create_topics.py` — crea topic `ticks` en Redpanda (idempotente)
- `ingestion/streaming/binance_producer.py` — WebSocket → Redpanda
- `ingestion/streaming/redpanda_consumer.py` — Redpanda → Postgres `raw.ticks`

**Validación:** después de unos segundos, `SELECT COUNT(*) FROM raw.ticks` crece. Comando útil: `make stream-tail` o equivalente psql.

### Fase 3 — Batch ingestion + lakehouse bronze

**Objetivo:** datos hourly/daily de fuentes REST, materializados como Parquet en MinIO + tablas `raw.*` en Postgres.

**Entregables:**
- `ingestion/batch/coingecko_loader.py` — pulls market snapshots
- `ingestion/batch/reddit_loader.py` — top posts de subreddits cripto, con flags `mentions_btc/eth/...`
- `ingestion/batch/fng_loader.py` — Fear & Greed index
- `ingestion/utils/minio_client.py` — wrapper boto3

**Validación:** archivos `.parquet` aparecen en buckets `bronze/...` (MinIO Console), tablas `raw.coingecko_markets`, `raw.reddit_posts`, `raw.fear_greed_index` populadas.

### Fase 4 — dbt staging + marts

**Objetivo:** modelo dimensional clásico sobre los datos crudos.

**Entregables:**
- `dbt_project/models/staging/*.sql` — 6 modelos staging (1 por fuente)
- `dbt_project/models/marts/core/` — `dim_coin`, `dim_date`, `fact_prices_hourly`, `fact_market_snapshot`, `fact_sentiment_daily`
- `dbt_project/models/marts/analytics/` — `mart_top_movers_daily`, `mart_social_vs_price`
- `dbt_project/models/*.yml` — pruebas (`unique`, `not_null`, `accepted_values`, `relationships`)

**Validación:** `dbt run` crea las tablas en `analytics_marts.*`, `dbt test` pasa todas las pruebas.

### Fase 5 — Machine Learning

**Objetivo:** convertir datos crudos en señales accionables.

**Entregables:**
- `ml/sentiment/vader_scorer.py` — corre VADER sobre `raw.reddit_posts.text`, escribe en `ml.reddit_sentiment` (compound, sentiment_label)
- `ml/anomaly/price_anomalies.py` — sobre `fact_prices_hourly`:
  - z-score rolling 168h
  - IsolationForest contamination=0.05
  - flag `is_anomaly_consensus` cuando ambos coinciden
- `ingestion/sql/init/03_ml_tables.sql` — tablas `ml.reddit_sentiment`, `ml.price_anomalies`
- `mart_anomaly_alerts.sql` (analytics) — junta anomalías con contexto de mercado y sentimiento

**Validación:** `SELECT COUNT(*) FROM ml.price_anomalies WHERE is_anomaly_consensus` devuelve > 0 (después de varias horas con datos).

### Fase 6 — Airflow

**Objetivo:** orquestar todo lo anterior sin scripts manuales.

**Entregables:**
- `airflow/dags/cryptopulse_hourly.py` — TaskGroups: ingest → transform → ml → validate → data_quality → notify
- `airflow/dags/cryptopulse_daily.py` — VADER (más costoso)
- `airflow/dags/cryptopulse_streaming_health.py` — sensor que falla si `raw.ticks` no recibió datos en X minutos
- `airflow/plugins/cryptopulse_common/` — helpers `python_module_task` y `dbt_task` para no repetir código

**Validación:** trigger manual del DAG hourly desde la UI o `airflow dags trigger`.

### Fase 7 — Data Quality (Great Expectations)

**Objetivo:** asegurar que los datos cumplen invariantes de negocio.

**Entregables:**
- `quality/suites.py` — define las suites:
  - `raw_ticks_suite` — price > 0, symbol in WHITELIST_BINANCE
  - `mart_anomaly_alerts_suite` — `severity_score >= 0`, columnas críticas no nulas
  - cross-column: `expect_column_pair_values_a_to_be_greater_than_b` (high vs low)
- `quality/run_checkpoint.py` — runner que carga el contexto, corre las suites elegidas, y emite resultados a `quality/results/`

**Notas:** GE 0.18 (no 1.x). Usa `add_or_update_expectation_suite()`. Hay dos whitelists de símbolos (Binance vs base) deliberadamente.

**Validación:** `python -m quality.run_checkpoint` imprime resumen y termina con exit code 0 si todo pasó.

### Fase 8 — Power BI

**Objetivo:** dashboard ejecutivo no técnico.

**Entregables:**
- `ingestion/sql/init/04_bi_views.sql` — 5 vistas estables (`bi.v_kpi_latest`, `bi.v_price_hourly`, `bi.v_anomaly_alerts`, `bi.v_sentiment_daily`, `bi.v_market_snapshot_latest`)
- `dashboard/powerbi/queries.m` — 6 Power Query (M) snippets
- `dashboard/powerbi/measures.dax` — 39 medidas DAX
- `dashboard/powerbi/layout_spec.md` — paint-by-numbers de las 4 páginas
- `dashboard/powerbi/README.md` — guía de armado

**Páginas del dashboard:**
1. Executive Summary (KPI cards + line normalizado + bar de alertas + top movers)
2. Price Anomalies (line con markers + tabla log + donut por detector)
3. Sentiment Tracker (Fear&Greed + VADER + Reddit posts/día)
4. Market Overview (tabla tipo CoinGecko + bar share + KPIs)

**Validación:** `Home → Refresh` en Power BI Desktop sin error, KPI cards muestran números (no Blank).

### Fase 9 — Streamlit Lab

**Objetivo:** app web interactiva complementaria al PBI, con un agente IA.

**Entregables:**
- `dashboard/streamlit_app.py` — home con sidebar que verifica Postgres y la API key del LLM
- `dashboard/pages/01_Live_Tick_Tail.py` — auto-refresh cada N segundos del tail de `raw.ticks`, semáforo de salud por símbolo (verde <5 min, amarillo <15 min, rojo ≥15 min)
- `dashboard/pages/02_Alert_Explainer.py` — selector de alerta + mini-gráfico de contexto + botón "Explicar con IA"
- `dashboard/lib/db.py` — wrappers con `st.cache_resource` (singleton de PgClient) y `st.cache_data(ttl=...)` por query, recovery automático ante `transaction aborted`
- `dashboard/lib/llm.py` — cliente Anthropic + prompt builder estructurado

**Diseño del prompt:** sistema = "eres analista cuantitativo cripto"; usuario = tabla markdown con metadata + ventana de precio horario. Modelo devuelve markdown con secciones fijas: Veredicto / Señales / Contexto / Hipótesis / Qué vigilar.

**Validación:** `streamlit run dashboard/streamlit_app.py`, navegar entre pages, click "Explicar" → respuesta de Claude en pantalla.

### Fase 10 — Telegram + CI/CD

**Objetivo:** alertar push + asegurar calidad del repo en cada PR.

**Entregables:**
- `alerts/telegram_notifier.py` — lee `bi.v_anomaly_alerts`, dedup contra `alerts.telegram_sent`, manda HTTP POST al Bot API
- `ingestion/sql/init/05_alerts_tables.sql` — schema `alerts` + tabla de dedup con PRIMARY KEY (`alert_key`)
- DAG hourly: nueva TaskGroup `notify` con `notify_telegram` después de `data_quality`
- `.github/workflows/ci.yml` — instala Python + deps, corre `ruff check` + `pytest -m "not integration"`

**Diseño del mensaje:** HTML parse-mode, sección básica (símbolo, hora, precio, retorno, z-score, severidad, F&G, Reddit, VADER) + opcional bloque generado por LLM (si `ANTHROPIC_API_KEY` está set).

**Validación:** smoke test `python -c "..."`; al cabo de horas el DAG dispara mensajes reales.

### Fase 11 — Documentación + e2e

**Objetivo:** cerrar el proyecto entregable.

**Entregables:**
- `README.md` reescrito (overview, badges, quickstart, fases)
- `docs/RUNBOOK.md` — runbook operacional + 11 gotchas resueltos
- `docs/GUIA_COMPLETA.md` — este documento
- `docs/screenshots/` — guía de capturas que faltan por subir

**Validación:** correr el checklist e2e de RUNBOOK.md: 15 ítems verdes.

---

## 7. Funciones y módulos clave

Una guía rápida para alguien que abre el repo por primera vez. Por orden de importancia.

### `ingestion/utils/config.py` — la fuente de verdad de configuración

Todo el código importa `from ingestion.utils.config import settings`. Es un objeto `pydantic-settings` que lee `.env` UNA vez, cachea con `lru_cache`, y expone properties tipadas. Si añades una variable, agrégala a la clase `Settings`.

### `ingestion/utils/pg_client.py` — capa thin sobre psycopg2

`PgClient` con `.conn` (lazy connect), `.transaction()` (context manager con commit/rollback automático), `.execute_script()` (SQL desde archivo), `.upsert_dataframe()` (batch via `execute_values`). Todo el resto del código accede a Postgres a través de este cliente.

### `ingestion/utils/pg_bootstrap.py` — aplicador idempotente

Recorre `ingestion/sql/init/*.sql` en orden alfabético y los ejecuta vía psycopg2. `01_init_schemas.sql` está en `SKIP_BY_DEFAULT` porque usa metacomandos psql (lo corre el contenedor en su init). Acepta `--only <file>` y `--force-all`.

### `ml/anomaly/price_anomalies.py` — el corazón de Phase 5

Carga `analytics_marts.fact_prices_hourly`, calcula z-score rolling y entrena IsolationForest, escribe a `ml.price_anomalies` con flags por detector + `is_anomaly_consensus`. Ese consensus es lo que termina disparando Telegram.

### `dashboard/lib/db.py` — bridge Streamlit ↔ Postgres

Decora con `@st.cache_resource` el cliente y con `@st.cache_data(ttl=...)` cada query. Implementa `_safe_reset()` para recuperarse del `transaction aborted` que pasa cuando una query falla y deja la conexión en estado roto.

### `dashboard/lib/llm.py` — agente del Alert Explainer

Singleton del cliente Anthropic con `@st.cache_resource`. La función central `build_user_prompt(ctx)` toma una alerta + ventana de precio y produce un prompt rico. `explain_alert(ctx)` envía y devuelve markdown listo para `st.markdown()`. Maneja gracefully que falte la API key o el package.

### `alerts/telegram_notifier.py` — de DB a Telegram

`fetch_pending_alerts()` con dedup vía LEFT JOIN contra `alerts.telegram_sent`. `build_basic_message()` arma HTML. `maybe_add_llm_summary()` enriquece si hay key. `mark_sent()` registra (idempotente con `ON CONFLICT DO NOTHING`).

### `airflow/dags/cryptopulse_hourly.py` — el director de orquesta

DAG con cron `15 * * * *` (cada hora al minuto 15). 6 TaskGroups encadenados. Usa los helpers `python_module_task` y `dbt_task` del plugin para no repetir `cwd`/`env` en cada task.

---

## 8. Operación día a día

### 8.1. Cheat sheet de comandos frecuentes

```powershell
# Salud del stack
docker compose ps

# Ver ticks recientes
docker compose exec postgres psql -U cryptopulse -d cryptopulse -c \
  "SELECT symbol, MAX(event_time) FROM raw.ticks GROUP BY 1 ORDER BY 2 DESC;"

# Refrescar todo silver+gold a mano
python -m ingestion.batch.coingecko_loader ; python -m ingestion.batch.fng_loader
cd dbt_project ; dbt run ; dbt test ; cd ..

# Re-aplicar las vistas BI (si Power BI tira "key didn't match")
python -m ingestion.utils.pg_bootstrap --only 04_bi_views.sql

# Disparar Airflow manualmente
docker compose exec airflow-scheduler airflow dags trigger cryptopulse_hourly

# Mandar alertas pendientes
python -m alerts.telegram_notifier --lookback-hours 24 --min-severity 1

# Modo debug Telegram (no envía nada, solo loguea)
python -m alerts.telegram_notifier --dry-run --lookback-hours 24 --min-severity 0
```

### 8.2. Cómo agregar un símbolo nuevo

1. Editar `.env` → `TRACKED_SYMBOLS=BTCUSDT,ETHUSDT,...,NUEVOUSDT`
2. Editar `ingestion/utils/config.py` → property `coingecko_ids` (mapping `BTCUSDT → bitcoin`, etc.) — agregar el nuevo
3. Reiniciar producer: `Ctrl+C` en el terminal de `binance_producer` y volver a lanzarlo
4. Esperar a la siguiente corrida del DAG hourly (o triggerla manual)
5. Verificar que `dim_coin` lo incluye después del próximo `dbt run`

### 8.3. Cómo añadir una nueva vista BI

1. Agregar el `CREATE OR REPLACE VIEW bi.v_nueva AS …` al final de `04_bi_views.sql`
2. `python -m ingestion.utils.pg_bootstrap --only 04_bi_views.sql`
3. En Power BI: `Home → Transform data → New Source → PostgreSQL → bi.v_nueva`
4. Renombrar la query y cargar
5. Si genera nuevas dimensiones, crear las relaciones en Model view

### 8.4. Cómo apagar y volver a prender

```powershell
# Apagar (los datos persisten en data/postgres y data/minio)
docker compose down

# Apagar y BORRAR datos (cuidado)
docker compose down -v
Remove-Item data/postgres/* -Recurse
Remove-Item data/minio/* -Recurse

# Volver a prender
docker compose up -d
python -m ingestion.utils.pg_bootstrap   # re-aplica scripts post-init
```

---

## 9. Troubleshooting

> Para la lista exhaustiva con causas y soluciones, ver [`RUNBOOK.md` sección 6](RUNBOOK.md#6-gotchas--fixes). Aquí va la versión condensada.

| Síntoma | Causa probable | Fix rápido |
|---|---|---|
| `relation "bi.v_*" does not exist` | Las vistas BI no fueron creadas o se borraron | `python -m ingestion.utils.pg_bootstrap --only 04_bi_views.sql` |
| Power BI: "key didn't match any rows" | Cache de schemas en PBI | Data source settings → Clear Permissions → reconectar |
| Streamlit: "current transaction is aborted" | Conexión psycopg2 en estado roto | Ya está parcheado en `dashboard/lib/db.py` con `_safe_reset()` |
| `ModuleNotFoundError: dashboard` en Streamlit | sys.path sin la raíz del repo | El shim ya está en `streamlit_app.py` y cada page; ejecuta SIEMPRE desde la raíz |
| Telegram: "chat not found" | El usuario no le mandó `/start` al bot | Buscar el bot en Telegram y mandarle `/start` |
| `streamlit` no en PATH | venv no instaló el binario en `Scripts/` | `python -m streamlit run dashboard/streamlit_app.py` |
| `add_or_update_expectation_suite` AttributeError | Versión GE incorrecta (1.x en vez de 0.18) | `pip install great-expectations==0.18.15` |
| File con null bytes después de Write | Mount Windows-Linux incompleto | Reescribir vía bash o `path.write_bytes(p.read_bytes().rstrip(b'\x00'))` |

---

## 10. Glosario para no técnicos

| Término | Qué significa en el contexto del proyecto |
|---|---|
| **Tick** | Una observación de precio individual recibida de Binance (puede haber decenas por minuto por símbolo) |
| **Bronze / Silver / Gold** | Capas del data lake. Bronze = crudo, Silver = limpio, Gold = listo para reportes |
| **Dimensional model** | Manera de organizar tablas para análisis: hechos (qué pasó) + dimensiones (atributos que describen) |
| **Fact / Dim** | "Fact" = tabla de eventos numéricos; "Dim" = tabla de atributos descriptivos |
| **Z-score** | Cuántas desviaciones estándar se aleja un retorno de la media histórica |
| **Isolation Forest** | Algoritmo ML que aísla outliers construyendo árboles aleatorios |
| **Consensus rule** | Marcar algo como anomalía solo si dos algoritmos independientes lo confirman |
| **Idempotente** | Una operación que da el mismo resultado sin importar cuántas veces la corras |
| **DAG** | Directed Acyclic Graph — el grafo de tareas de Airflow |
| **Multipage app (Streamlit)** | Una app Streamlit con varias páginas auto-detectadas desde un folder `pages/` |
| **Parse mode HTML** | El formato que usa Telegram para texto con `<b>`, `<code>`, etc. |
| **Cache de schemas (PBI)** | Power BI guarda la lista de schemas de Postgres la primera vez que conecta — después no se entera de schemas nuevos hasta que limpias permisos |

---

## 11. Próximas mejoras

Ideas concretas para extender el proyecto, ordenadas por impacto/esfuerzo.

### Cortas (1-3 horas)

- **`bi.v_coin_performance_30d`** — vista comparativa de retornos a 1d/7d/30d.
- **Tema visual de Power BI** — `theme.json` con paleta consistente.
- **Test integration** — prueba que levanta postgres con docker, corre `pg_bootstrap`, valida schemas creados.

### Medianas (1-2 días)

- **Backtest sencillo** en Streamlit: long en consensus negativa, hold N horas, calcula Sharpe.
- **Drill-through en Power BI** — desde alert → detail page con filtro `symbol + rango temporal`.
- **DBT exposures** — declarar las apps PBI/Streamlit como downstream consumers en el grafo de dbt.
- **Alembic / dbt-snapshot** sobre `dim_coin` para SCD tipo 2 cuando cambien atributos.

### Largas (1+ semana)

- **Despliegue en cloud** — Terraform para AWS (RDS + S3 + MWAA) o GCP equivalente.
- **Frontend React/Next.js** sustituyendo Streamlit para una experiencia más pulida.
- **Modelos de forecasting** — Prophet / Chronos para predicción a corto plazo, comparable contra retornos reales.
- **Feature store** — convertir `mart_anomaly_alerts` en un feature set reutilizable, con Feast o similar.

---

> **Autor:** Frago — `jeanpaulfrago10@gmail.com`
>
> Este proyecto es un portafolio. Cualquier feedback, issue o PR es bienvenido.
