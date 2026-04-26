"""
DAG — cryptopulse_daily
=======================
Tareas más pesadas que solo tiene sentido correr una vez por día:

  * VADER sentiment scoring sobre posts de Reddit del último día.
  * Freshness check de sources (`dbt source freshness`).
  * dbt docs regenerate (para dashboard estático).

Corre a las 03:10 UTC (después del DAG horario de las 03:15 se evita
colisión con la corrida de la 01 → más limpio en el scheduler).
"""
from __future__ import annotations

from datetime import datetime

from airflow import DAG

from cryptopulse_common import default_args, dbt_task, python_module_task


with DAG(
    dag_id="cryptopulse_daily",
    description="VADER sentiment scoring + dbt source freshness + docs",
    default_args=default_args,
    start_date=datetime(2026, 1, 1),
    schedule="10 3 * * *",            # 03:10 UTC todos los días
    catchup=False,
    max_active_runs=1,
    tags=["cryptopulse", "daily", "ml", "quality"],
) as dag:

    # --- 1. Freshness check — deben haber llegado datos frescos en las últimas horas
    dbt_freshness = dbt_task("dbt_source_freshness", "source freshness")

    # --- 2. VADER scoring sobre los posts recientes
    vader_score = python_module_task(
        task_id="vader_sentiment",
        module="ml.sentiment.vader_scorer",
        args="--lookback-days 2",          # día actual + anterior (garantiza idempotencia)
    )

    # --- 3. Refresh del stg_reddit_sentiment + mart_anomaly_alerts para que tomen nuevos scores
    dbt_run_sentiment_layer = dbt_task(
        "dbt_run_sentiment_layer",
        "run",
        select="stg_reddit_sentiment+",    # la view y todo lo que depende de ella
    )

    # --- 4. Tests finales
    dbt_test = dbt_task("dbt_test", "test", select="stg_reddit_sentiment+ mart_anomaly_alerts")

    dbt_freshness >> vader_score >> dbt_run_sentiment_layer >> dbt_test
