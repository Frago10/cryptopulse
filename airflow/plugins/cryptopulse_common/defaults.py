"""
Defaults compartidos para todos los DAGs de CryptoPulse.
"""
from __future__ import annotations

from datetime import timedelta

# Ruta DENTRO del contenedor Airflow donde está mapeado el proyecto.
# docker-compose monta ./ingestion, ./dbt_project, ./ml en /opt/airflow/
PROJECT_DIR = "/opt/airflow"

default_args = {
    "owner": "cryptopulse",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=30),
    # Fase 10 sobrescribirá esto con un hook de Telegram
    "on_failure_callback": None,
}
