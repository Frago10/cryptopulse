"""
quality.run_checkpoint
======================
Orquesta la ejecucion de todas las suites de Great Expectations definidas
en `quality/suites.py` contra Postgres y persiste resultados.

Uso manual:
    python -m quality.run_checkpoint
    python -m quality.run_checkpoint --suite raw_ticks
    python -m quality.run_checkpoint --fail-fast

Uso en Airflow:
    BashOperator -> `python -m quality.run_checkpoint`
    Exit code 0 = todas las suites criticas pasaron.
    Exit code 1 = al menos una suite critica fallo (el DAG se marca failed).

Notas:
  * Escrito contra Great Expectations 0.18.x (Fluent Datasources API).
  * Usamos EphemeralDataContext para no dejar YAMLs sueltos en disco.
    Las suites viven en codigo (ver suites.py) y los resultados se
    escriben como JSON en quality/results/<run_id>/.
  * Si no hay filas en una tabla (p.ej. ml.reddit_sentiment recien creada),
    las expectativas de contenido pasan vacuamente y la suite cuenta como
    OK. Solo fallaria si la tabla misma no existiera.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Silencia los warnings ruidosos de GE a nivel de import
os.environ.setdefault("GE_USAGE_STATISTICS_ENABLED", "FALSE")
warnings.filterwarnings("ignore", category=DeprecationWarning)

import great_expectations as gx  # noqa: E402
from great_expectations.core.expectation_configuration import (  # noqa: E402
    ExpectationConfiguration,
)

from quality.suites import SUITES  # noqa: E402


# --------------------------------------------------------------------------- #
# Configuracion
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "quality" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def _postgres_dsn() -> str:
    """
    Construye DSN SQLAlchemy a partir de env vars. Funciona igual
    corrido local (POSTGRES_HOST=localhost) o dentro de Airflow
    (POSTGRES_HOST=postgres).
    """
    user = os.getenv("POSTGRES_USER", "cryptopulse")
    pwd  = os.getenv("POSTGRES_PASSWORD", "changeme_in_prod")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db   = os.getenv("POSTGRES_DB", "cryptopulse")
    return f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}"


# --------------------------------------------------------------------------- #
# Validador por suite — API de GE 0.18.x
# --------------------------------------------------------------------------- #
def _validate_suite(
    context,
    datasource,
    suite_name: str,
    spec: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Construye un Validator sobre (schema.table) y ejecuta todas las
    expectativas de la suite. Retorna un dict resumen listo para JSON.
    """
    schema = spec["schema"]
    table  = spec["table"]
    builder = spec["builder"]

    # 1) Crea la suite en memoria
    suite = context.add_or_update_expectation_suite(
        expectation_suite_name=suite_name
    )
    for exp_type, kwargs in builder():
        suite.add_expectation(ExpectationConfiguration(
            expectation_type=exp_type,
            kwargs=kwargs,
        ))
    context.save_expectation_suite(suite)

    # 2) Registra (o reutiliza) el asset = schema.table
    asset_name = f"{schema}__{table}"
    try:
        asset = datasource.get_asset(asset_name)
    except LookupError:
        asset = datasource.add_table_asset(
            name=asset_name,
            table_name=table,
            schema_name=schema,
        )

    # 3) BatchRequest = "la tabla entera" (barrido completo)
    batch_request = asset.build_batch_request()

    validator = context.get_validator(
        batch_request=batch_request,
        expectation_suite_name=suite_name,
    )

    n = len(list(suite.expectations))
    print(f"  [gx] Running {n} expectations on {schema}.{table}")

    result = validator.validate()

    # 4) Normaliza salida
    per_exp = []
    for exp_result in result.results:
        per_exp.append({
            "type":     exp_result.expectation_config.expectation_type,
            "kwargs":   dict(exp_result.expectation_config.kwargs),
            "success":  bool(exp_result.success),
            "observed": _safe_observed(exp_result.result),
        })

    return {
        "suite":        suite_name,
        "schema":       schema,
        "table":        table,
        "success":      bool(result.success),
        "stats":        dict(result.statistics),
        "expectations": per_exp,
    }


def _safe_observed(result: Any) -> Dict[str, Any]:
    """Extrae solo los campos serializables del result del motor."""
    if not result:
        return {}
    out = {}
    for key in ("observed_value", "element_count", "unexpected_count",
                "unexpected_percent", "missing_count", "partial_unexpected_list"):
        if key in result:
            val = result[key]
            # Truncar listas grandes
            if isinstance(val, list) and len(val) > 10:
                val = val[:10] + [f"... +{len(val)-10} more"]
            out[key] = val
    return out


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(description="CryptoPulse data quality runner")
    parser.add_argument(
        "--suite",
        choices=sorted(SUITES.keys()),
        help="Corre solo una suite (default: todas)",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Aborta en la primera suite critica que falle",
    )
    args = parser.parse_args()

    suites_to_run = (
        {args.suite: SUITES[args.suite]} if args.suite else SUITES
    )

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = RESULTS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"[ge] run_id={run_id} | suites={list(suites_to_run.keys())}")
    print(f"[ge] Results -> {run_dir}")

    # Context efimero + datasource unico reutilizado por todas las suites
    context = gx.get_context(mode="ephemeral")
    datasource = context.sources.add_postgres(
        name="cryptopulse_pg",
        connection_string=_postgres_dsn(),
    )

    all_results: List[Dict[str, Any]] = []
    critical_failures: List[str] = []

    for name, spec in suites_to_run.items():
        print(f"\n--- Suite: {name}  ({'CRITICAL' if spec['critical'] else 'soft'}) ---")
        try:
            res = _validate_suite(context, datasource, name, spec)
        except Exception as exc:  # noqa: BLE001
            print(f"  [gx] ERROR durante validacion: {exc}")
            res = {
                "suite": name, "success": False,
                "error": str(exc),
                "schema": spec["schema"], "table": spec["table"],
            }
        all_results.append(res)

        # Print compacto
        if res.get("success"):
            print(f"  [gx] OK  {res.get('stats', {})}")
        else:
            print(f"  [gx] FAIL  {res.get('stats', {})}")
            for exp in res.get("expectations", []):
                if not exp["success"]:
                    print(f"    - {exp['type']}({exp['kwargs']})"
                          f"  observed={exp['observed']}")
            if spec["critical"]:
                critical_failures.append(name)
                if args.fail_fast:
                    break

    # Persistir resultados en JSON (audit trail)
    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(
        {"run_id": run_id, "results": all_results,
         "critical_failures": critical_failures},
        indent=2, default=str,
    ))
    print(f"\n[ge] Summary -> {summary_path}")

    # Exit code
    if critical_failures:
        print(f"\n[ge] SUITES CRITICAS FALLADAS: {critical_failures}")
        return 1
    print("\n[ge] Todas las suites criticas OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
