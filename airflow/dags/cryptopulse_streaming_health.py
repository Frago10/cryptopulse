"""
DAG — cryptopulse_streaming_health
==================================
Chequeo ligero cada 15 minutos que verifica que el consumer de Binance
está vivo y escribiendo ticks a `raw.ticks`. Si no vino nada en los
últimos 10 minutos, la task falla y el callback (Fase 10) mandará
alerta a Telegram.

No depende de los batch DAGs — corre en paralelo 24x7.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from cryptopulse_common import default_args


STALE_MINUTES = 10     # umbral para marcar el stream como "muerto"


def _check_tick_freshness(**context) -> None:
    """
    Consulta el max(event_time) de raw.ticks y falla si es > STALE_MINUTES.
    """
    from airflow.providers.postgres.hooks.postgres import PostgresHook

    hook = PostgresHook(postgres_conn_id="cryptopulse_pg")
    sql = """
        SELECT
            MAX(event_time)                          AS last_tick,
            NOW()                                    AS now_utc,
            EXTRACT(EPOCH FROM NOW() - MAX(event_time)) / 60.0 AS minutes_since_last
        FROM raw.ticks
    """
    row = hook.get_first(sql)
    if row is None or row[0] is None:
        raise ValueError("raw.ticks vacia — el consumer nunca escribio datos?")

    last_tick, now_utc, minutes = row
    context["ti"].xcom_push(key="last_tick", value=str(last_tick))
    context["ti"].xcom_push(key="minutes_since_last", value=float(minutes))

    print(f"[streaming_health] last_tick={last_tick} | ahora={now_utc} | "
          f"lag={minutes:.2f} min (umbral={STALE_MINUTES} min)")

    if minutes > STALE_MINUTES:
        raise ValueError(
            f"Stream STALE: ultimo tick hace {minutes:.1f} minutos "
            f"(umbral: {STALE_MINUTES} min). Revisar consumer/producer."
        )


with DAG(
    dag_id="cryptopulse_streaming_health",
    description="Monitor de salud del stream Binance -> raw.ticks (cada 15 min)",
    default_args={
        **default_args,
        "retries": 1,              # no tiene sentido reintentar mucho un monitor
        "retry_delay": timedelta(minutes=2),
    },
    start_date=datetime(2026, 1, 1),
    schedule="*/15 * * * *",       # cada 15 minutos
    catchup=False,
    max_active_runs=1,
    tags=["cryptopulse", "monitor", "streaming"],
) as dag:

    check_tick_freshness = PythonOperator(
        task_id="check_tick_freshness",
        python_callable=_check_tick_freshness,
    )
