"""
CryptoPulse — utilidades compartidas entre DAGs.

Exportamos helpers para:
  * Defaults de DAG (retries, emails, callbacks)
  * Wrappers de BashOperator con el cwd y env correctos
  * Callbacks (log estructurado, hook de Telegram para Fase 10)
"""
from cryptopulse_common.defaults import default_args, PROJECT_DIR
from cryptopulse_common.operators import python_module_task, dbt_task

__all__ = ["default_args", "PROJECT_DIR", "python_module_task", "dbt_task"]
