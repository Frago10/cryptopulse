"""
Helper thin para Postgres: conexión, upsert de DataFrames y ejecución
de scripts SQL desde archivo.

Filosofía:
  - Una sola conexión por proceso (reutilizable) via `get_pg()`.
  - No usamos SQLAlchemy — psycopg2 directo es más ligero y nos da
    acceso a `execute_values` (batch inserts rapidísimos).
  - Idempotencia vía ON CONFLICT DO NOTHING/UPDATE cuando hace sentido.

Convenciones:
  - Siempre autocommit=False: el caller controla la transacción.
  - Los errores se propagan al caller pero loggeamos contexto antes.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Optional, Sequence

import pandas as pd
import psycopg2
from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import execute_values

from ingestion.utils.config import settings
from ingestion.utils.logging_config import get_logger

log = get_logger(__name__)


class PgClient:
    """Cliente Postgres con reconexión perezosa."""

    def __init__(self) -> None:
        self._conn: Optional[PgConnection] = None

    # ---- Conexión ----
    @property
    def conn(self) -> PgConnection:
        if self._conn is None or self._conn.closed:
            log.info("pg.connect", host=settings.POSTGRES_HOST, db=settings.POSTGRES_DB)
            self._conn = psycopg2.connect(settings.postgres_dsn)
        return self._conn

    def close(self) -> None:
        if self._conn and not self._conn.closed:
            self._conn.close()

    @contextmanager
    def transaction(self):
        """Context manager: commit al salir OK, rollback si hay excepción."""
        c = self.conn
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise

    # ---- Ejecución de SQL ----
    def execute_script(self, sql_path: str | Path) -> None:
        """Ejecuta un archivo .sql completo (sin meta-comandos tipo \\c)."""
        path = Path(sql_path)
        sql = path.read_text(encoding="utf-8")
        log.info("pg.execute_script", path=str(path), bytes=len(sql))
        with self.transaction() as c, c.cursor() as cur:
            cur.execute(sql)

    def execute(self, sql: str, params: Optional[Sequence] = None) -> None:
        with self.transaction() as c, c.cursor() as cur:
            cur.execute(sql, params)

    # ---- Upsert de DataFrames ----
    def upsert_dataframe(
        self,
        df: pd.DataFrame,
        *,
        table: str,
        columns: Sequence[str],
        conflict_cols: Optional[Sequence[str]] = None,
        update_cols: Optional[Sequence[str]] = None,
        page_size: int = 500,
    ) -> int:
        """
        Inserta `df` en `table` usando `execute_values`.

        Args:
            df: DataFrame con las columnas requeridas (extras se ignoran).
            table: nombre completo (schema.table) de destino.
            columns: lista ordenada de columnas a insertar.
            conflict_cols: si se indica, hace ON CONFLICT (...) sobre esas columnas.
            update_cols: si se indica junto a conflict_cols, hace DO UPDATE SET col=EXCLUDED.col.
                         Si conflict_cols está seteado pero update_cols no, hace DO NOTHING.
            page_size: batch interno de execute_values.

        Returns:
            Cantidad de filas enviadas a Postgres (no necesariamente insertadas
            si hay DO NOTHING; Postgres no nos devuelve ese detalle sin RETURNING).
        """
        if df.empty:
            log.warning("pg.upsert.empty", table=table)
            return 0

        missing = [c for c in columns if c not in df.columns]
        if missing:
            raise ValueError(f"DataFrame missing columns for {table}: {missing}")

        # Quedarnos solo con las columnas declaradas, en el orden pedido
        sub = df[list(columns)]
        # Convertir NaT/NaN -> None para que psycopg2 los serialice como NULL
        records = [tuple(None if pd.isna(v) else v for v in row) for row in sub.itertuples(index=False, name=None)]

        cols_sql = ", ".join(columns)
        conflict_sql = ""
        if conflict_cols:
            cc = ", ".join(conflict_cols)
            if update_cols:
                sets = ", ".join(f"{c}=EXCLUDED.{c}" for c in update_cols)
                conflict_sql = f" ON CONFLICT ({cc}) DO UPDATE SET {sets}"
            else:
                conflict_sql = f" ON CONFLICT ({cc}) DO NOTHING"

        sql = f"INSERT INTO {table} ({cols_sql}) VALUES %s{conflict_sql}"

        with self.transaction() as c, c.cursor() as cur:
            execute_values(cur, sql, records, page_size=page_size)

        log.info("pg.upsert.ok", table=table, rows=len(records))
        return len(records)

    def truncate(self, table: str) -> None:
        """Vacía una tabla (útil para snapshots reemplazables)."""
        log.info("pg.truncate", table=table)
        self.execute(f"TRUNCATE TABLE {table}")

    def count(self, table: str) -> int:
        with self.conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            return cur.fetchone()[0]


# ---- Singleton ----
_client: Optional[PgClient] = None


def get_pg() -> PgClient:
    global _client
    if _client is None:
        _client = PgClient()
    return _client
