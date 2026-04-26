"""
DAG — cryptopulse_hourly
========================
Pipeline principal que corre cada hora. Refresca el warehouse con los
datos batch recientes y las tablas de ML.

Flujo (TaskGroups):

  ingest     -> transform     -> ml              -> validate -> data_quality
   ├ coingecko  ├ dbt_deps       ├ anomalies        └ dbt_test   └ ge_validate
   ├ fng        ├ run_staging    └ refresh_mart
   └ reddit     └ run_marts         anomaly_alerts

Nota:
  El scoring VADER vive en `cryptopulse_daily` — es costoso y no
  necesita correr cada hora. `ml_anomalies` sí: buscamos detectar
  spikes horarios rápidos. Las validaciones de Great Expectations
  corren AL FINAL — si dbt ya aprobó schema/unicidad pero las
  distribuciones están raras (price=0, symbol fuera de whitelist),
  el DAG falla acá para avisar que hay datos sospechosos.
"""
from __future__ import annotations

from datetime import datetime

from airflow import DAG
from airflow.utils.task_group import TaskGroup

from cryptopulse_common import default_args, dbt_task, python_module_task


with DAG(
    dag_id="cryptopulse_hourly",
    description="Ingesta batch + dbt silver/gold + anomaly detection (hora a hora)",
    default_args=default_args,
    start_date=datetime(2026, 1, 1),
    schedule="15 * * * *",            # cada hora al minuto 15 (amortigua latencia de APIs)
    catchup=False,
    max_active_runs=1,
    tags=["cryptopulse", "hourly", "batch", "ml"],
) as dag:

    # --------------------------------------------------------------------- #
    # 1. Ingest — pobla raw.* (paralelo)
    # --------------------------------------------------------------------- #
    with TaskGroup("ingest") as ingest:
        load_coingecko = python_module_task(
            task_id="load_coingecko",
            module="ingestion.batch.coingecko_loader",
        )
        load_fng = python_module_task(
            task_id="load_fng",
            module="ingestion.batch.fng_loader",
        )
        load_reddit = python_module_task(
            task_id="load_reddit",
            module="ingestion.batch.reddit_loader",
        )

    # --------------------------------------------------------------------- #
    # 2. Transform — dbt staging + marts (excepto mart_anomaly_alerts)
    # --------------------------------------------------------------------- #
    with TaskGroup("transform") as transform:
        dbt_deps = dbt_task("dbt_deps", "deps")

        dbt_run_staging = dbt_task(
            "dbt_run_staging",
            "run",
            select="path:models/staging",
        )

        # Corremos los marts SIN mart_anomaly_alerts, que depende de ml.*
        dbt_run_marts_core = dbt_task(
            "dbt_run_marts",
            "run",
            select="path:models/marts --exclude mart_anomaly_alerts",
        )

        dbt_deps >> dbt_run_staging >> dbt_run_marts_core

    # --------------------------------------------------------------------- #
    # 3. ML — anomalías sobre fact_prices_hourly recién refrescado
    # --------------------------------------------------------------------- #
    with TaskGroup("ml") as ml:
        detect_anomalies = python_module_task(
            task_id="detect_price_anomalies",
            module="ml.anomaly.price_anomalies",
            args="--lookback-hours 168",   # 7 días rolling
        )

        refresh_mart = dbt_task(
            "dbt_run_mart_anomaly_alerts",
            "run",
            select="mart_anomaly_alerts",
        )

        detect_anomalies >> refresh_mart

    # --------------------------------------------------------------------- #
    # 4. Validate — dbt test completo
    # --------------------------------------------------------------------- #
    dbt_test_all = dbt_task("dbt_test", "test")

    # --------------------------------------------------------------------- #
    # 5. Data Quality — Great Expectations sobre raw + gold
    #    Corre DESPUES de dbt_test: verifica distribuciones y rangos de
    #    negocio (no solo schema). Falla el DAG si alguna suite critica
    #    detecta datos fuera de rango (p.ej. price=0 o symbol desconocido).
    # --------------------------------------------------------------------- #
    with TaskGroup("data_quality") as data_quality:
        ge_validate = python_module_task(
            task_id="great_expectations_validate",
            module="quality.run_checkpoint",
        )

    # --------------------------------------------------------------------- #
    # 6. Notify — Telegram (Fase 10)
    #    Lee bi.v_anomaly_alerts, dedup contra alerts.telegram_sent y
    #    manda solo las nuevas con consensus + severity >= 3. Idempotente:
    #    re-correr la task no duplica mensajes.
    # --------------------------------------------------------------------- #
    with TaskGroup("notify") as notify:
        notify_telegram = python_module_task(
            task_id="notify_telegram",
            module="alerts.telegram_notifier",
            args="--min-severity 3 --lookback-hours 6",
        )

    # --------------------------------------------------------------------- #
    # Dependencias entre TaskGroups
    # --------------------------------------------------------------------- #
    ingest >> transform >> ml >> dbt_test_all >> data_quality >> notify
