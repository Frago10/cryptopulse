"""
Bootstrap de Postgres: aplica los scripts .sql de ingestion/sql/init/ en orden.

Idempotente gracias a CREATE TABLE IF NOT EXISTS y CREATE INDEX IF NOT EXISTS
en los propios scripts. Se puede correr cuantas veces uno quiera.

IMPORTANTE — separación de responsabilidades:
  * 01_init_schemas.sql se ejecuta UNA sola vez vía docker-entrypoint-initdb.d
    (lo corre psql dentro del contenedor, por eso puede usar \c, \dt, etc.).
    Ese script ya dejó creados schemas, raw.ticks y la DB airflow.
  * Este bootstrap (vía psycopg2) solo corre los scripts posteriores
    — por defecto 02_*.sql, 03_*.sql, ... — que deben ser SQL puro
    (sin meta-comandos de psql).

Por eso 01_init_schemas.sql queda SKIPEADO explícitamente.

Uso:
    python -m ingestion.utils.pg_bootstrap
    python -m ingestion.utils.pg_bootstrap --only 02_raw_tables.sql
    python -m ingestion.utils.pg_bootstrap --force-all
"""
from __future__ import annotations

import argparse
from pathlib import Path

from ingestion.utils.config import PROJECT_ROOT
from ingestion.utils.logging_config import configure_logging, get_logger
from ingestion.utils.pg_client import get_pg

log = get_logger(__name__)

SQL_DIR = PROJECT_ROOT / "ingestion" / "sql" / "init"

# Scripts que NO deben correrse por psycopg2 — los corre Docker en el init
SKIP_BY_DEFAULT = {"01_init_schemas.sql"}


def list_scripts(only: str | None = None, force_all: bool = False) -> list[Path]:
    if not SQL_DIR.exists():
        raise FileNotFoundError(f"No existe el directorio {SQL_DIR}")
    scripts = sorted(SQL_DIR.glob("*.sql"))
    if only:
        scripts = [p for p in scripts if p.name == only]
        if not scripts:
            raise FileNotFoundError(f"No se encontro {only} en {SQL_DIR}")
    elif not force_all:
        skipped = [p for p in scripts if p.name in SKIP_BY_DEFAULT]
        if skipped:
            log.info(
                "bootstrap.skip",
                files=[p.name for p in skipped],
                reason="docker-entrypoint-initdb.d (uses psql meta-commands)",
            )
        scripts = [p for p in scripts if p.name not in SKIP_BY_DEFAULT]
    return scripts


def run(only: str | None = None, force_all: bool = False) -> None:
    configure_logging()
    pg = get_pg()
    scripts = list_scripts(only=only, force_all=force_all)
    log.info("bootstrap.start", count=len(scripts), dir=str(SQL_DIR))
    for script in scripts:
        log.info("bootstrap.applying", file=script.name)
        pg.execute_script(script)
    log.info("bootstrap.done", applied=[p.name for p in scripts])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Aplica scripts SQL de init.")
    parser.add_argument("--only", help="Ejecutar solo este archivo (nombre)")
    parser.add_argument(
        "--force-all",
        action="store_true",
        help="Aplicar TODOS los scripts (incluye 01_*, que tiene metacomandos psql)",
    )
    args = parser.parse_args()
    run(only=args.only, force_all=args.force_all)
