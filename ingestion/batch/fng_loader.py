"""
Fear & Greed Index loader — alternative.me
Endpoint público sin autenticación.

Doc: https://alternative.me/crypto/fear-and-greed-index/

Respuesta esperada:
{
  "name": "Fear and Greed Index",
  "data": [
    {"value": "65", "value_classification": "Greed", "timestamp": "1713724800",
     "time_until_update": "25200"}
  ],
  "metadata": {...}
}
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import requests

from ingestion.utils.config import settings
from ingestion.utils.logging_config import configure_logging, get_logger
from ingestion.utils.minio_client import get_minio
from ingestion.utils.pg_client import get_pg

log = get_logger(__name__)

SOURCE = "fng"
DATASET = "fear_greed_index"

PG_TABLE = "raw.fear_greed_index"
PG_COLUMNS = ["index_date", "value", "category", "time_until_update", "ingested_at"]


def fetch(limit: int = 30) -> list[dict]:
    """Trae los últimos `limit` días del índice.

    Notas sobre el endpoint (alternative.me):
    - El URL DEBE terminar en '/' — sin slash devuelve solo 1 registro.
    - NO enviar `format=json` — actualmente (2026-04) esa query también
      hace que devuelva solo 1 registro. El default ya es JSON.
    """
    # Garantizar slash final (hallazgo de debugging: sin él, la API devuelve 1 fila)
    url = settings.FNG_API_URL
    if not url.endswith("/"):
        url += "/"

    params = {"limit": limit}
    log.info("fng.fetch.start", url=url, limit=limit)
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    data = payload.get("data", [])
    log.info("fng.fetch.ok", count=len(data))
    return data


def transform(raw: list[dict]) -> pd.DataFrame:
    if not raw:
        return pd.DataFrame()

    df = pd.DataFrame(raw)
    df["value"] = df["value"].astype(int)
    df["timestamp"] = pd.to_datetime(df["timestamp"].astype(int), unit="s", utc=True)
    df = df.rename(columns={"timestamp": "index_date", "value_classification": "category"})

    df["_ingested_at"] = datetime.now(timezone.utc)
    df["_source"] = SOURCE
    df["_dataset"] = DATASET
    return df[["index_date", "value", "category", "time_until_update",
               "_ingested_at", "_source", "_dataset"]]


def persist(df: pd.DataFrame, partition_ts: datetime | None = None) -> str:
    return get_minio().write_parquet(
        df,
        source=SOURCE,
        dataset=DATASET,
        partition_ts=partition_ts,
        overwrite_partition=True,
    )


def persist_to_postgres(df: pd.DataFrame) -> int:
    """
    Upsert en raw.fear_greed_index. Como el endpoint devuelve el histórico
    de los últimos N días, usamos ON CONFLICT sobre index_date para no
    duplicar cuando el loader corra varias veces al día.

    NOTA: la tabla no tiene PK declarada; creamos una UNIQUE constraint
    lazy aquí para soportar el ON CONFLICT. Es idempotente.
    """
    if df.empty:
        return 0
    df2 = df.copy().rename(columns={"_ingested_at": "ingested_at"})
    for col in PG_COLUMNS:
        if col not in df2.columns:
            df2[col] = None

    pg = get_pg()
    # Asegurar UNIQUE(index_date) para habilitar ON CONFLICT (idempotente)
    pg.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_fng_date "
        "ON raw.fear_greed_index (index_date)"
    )
    return pg.upsert_dataframe(
        df2,
        table=PG_TABLE,
        columns=PG_COLUMNS,
        conflict_cols=["index_date"],
        update_cols=["value", "category", "time_until_update", "ingested_at"],
    )


def run() -> str:
    configure_logging()
    raw = fetch(limit=30)
    df = transform(raw)
    key = persist(df)
    pg_rows = persist_to_postgres(df)
    log.info("fng.run.complete", rows=len(df), key=key, pg_rows=pg_rows)
    return key


if __name__ == "__main__":
    run()
