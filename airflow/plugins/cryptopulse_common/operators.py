"""
Wrappers de operators para no repetir `cwd` + `env` en cada task.

Ambos helpers devuelven un `BashOperator` listo para usarse en un DAG.
El env por defecto hereda del proceso (que ya trae POSTGRES_HOST,
DBT_PROFILES_DIR, etc. inyectados por docker-compose).
"""
from __future__ import annotations

from typing import Optional

from airflow.operators.bash import BashOperator

from cryptopulse_common.defaults import PROJECT_DIR


def python_module_task(
    task_id: str,
    module: str,
    *,
    args: str = "",
    cwd: str = PROJECT_DIR,
    **kwargs,
) -> BashOperator:
    """
    Ejecuta `python -m <module> <args>` en el cwd indicado.

    Ejemplo:
        python_module_task(
            task_id="load_coingecko",
            module="ingestion.batch.coingecko_loader",
        )
    """
    cmd = f"python -m {module} {args}".strip()
    return BashOperator(
        task_id=task_id,
        bash_command=cmd,
        cwd=cwd,
        **kwargs,
    )


def dbt_task(
    task_id: str,
    action: str,
    *,
    select: Optional[str] = None,
    target: str = "dev",
    cwd: str = f"{PROJECT_DIR}/dbt_project",
    **kwargs,
) -> BashOperator:
    """
    Ejecuta `dbt <action> [--select <sel>] --target <target>`.

    Ejemplo:
        dbt_task("dbt_run_staging", "run", select="staging")
        dbt_task("dbt_test_marts", "test", select="marts")
    """
    parts = [f"dbt {action}", f"--target {target}"]
    if select:
        parts.append(f"--select {select}")
    cmd = " ".join(parts)
    return BashOperator(
        task_id=task_id,
        bash_command=cmd,
        cwd=cwd,
        **kwargs,
    )
