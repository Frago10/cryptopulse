"""
CoinGecko loader — extrae market data de las top N monedas y la deja
en bronze/coingecko/market_data/dt=.../hh=...

API usada (endpoint público, sin autenticación):
  GET /coins/markets?vs_currency=usd&order=market_cap_desc&per_page=100

Documentación: https://docs.coingecko.com/reference/coins-markets

Patrón de diseño:
    fetch()     -> pd.DataFrame (raw)
    transform() -> pd.DataFrame (tipado y con metadata)
    persist()   -> s3 key

Este mismo patrón se reutiliza en todos los loaders. Es el estándar
"Extract / Transform-light / Load" típico del bronze layer: pocas
transformaciones, solo parseo y enriquecimiento mínimo.
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

SOURCE = "coingecko"
DATASET = "market_data"

# Columnas que persistimos en raw.coingecko_markets (orden importa)
PG_TABLE = "raw.coingecko_markets"
PG_COLUMNS = [
    "id", "symbol", "name", "image",
    "current_price", "market_cap", "market_cap_rank", "fully_diluted_valuation",
    "total_volume", "high_24h", "low_24h",
    "price_change_24h", "price_change_percentage_24h",
    "price_change_percentage_1h_in_currency",
    "price_change_percentage_24h_in_currency",
    "price_change_percentage_7d_in_currency",
    "market_cap_change_24h", "market_cap_change_percentage_24h",
    "circulating_supply", "total_supply", "max_supply",
    "ath", "ath_change_percentage", "ath_date",
    "atl", "atl_change_percentage", "atl_date",
    "last_updated", "ingested_at",
]


def fetch(per_page: int = 100, page: int = 1) -> list[dict]:
    """Llama al endpoint /coins/markets y devuelve la lista cruda."""
    url = f"{settings.COINGECKO_API_URL}/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": per_page,
        "page": page,
        "price_change_percentage": "1h,24h,7d",
        "sparkline": "false",
    }
    log.info("coingecko.fetch.start", url=url, per_page=per_page, page=page)
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    log.info("coingecko.fetch.ok", count=len(data))
    return data


def transform(raw: list[dict]) -> pd.DataFrame:
    """Tipado mínimo y enriquecimiento con metadata de ingesta."""
    if not raw:
        return pd.DataFrame()

    df = pd.DataFrame(raw)
    now = datetime.now(timezone.utc)

    # Enriquecer con columnas de linaje/observabilidad
    df["_ingested_at"] = now
    df["_source"] = SOURCE
    df["_dataset"] = DATASET

    # Normalizar columnas de fechas ISO
    for col in ("last_updated", "ath_date", "atl_date"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")

    return df


def persist(df: pd.DataFrame, partition_ts: datetime | None = None) -> str:
    """Escribe el DataFrame como Parquet en MinIO."""
    minio = get_minio()
    return minio.write_parquet(
        df,
        source=SOURCE,
        dataset=DATASET,
        partition_ts=partition_ts,
        overwrite_partition=True,
    )


def persist_to_postgres(df: pd.DataFrame) -> int:
    """
    Hidrata la tabla raw.coingecko_markets en Postgres.

    Como este dataset es un snapshot cada hora, se inserta tal cual. Si
    eventualmente querés deduplicar por (id, ingested_at::hour) se puede
    agregar una UNIQUE constraint. Por ahora preferimos conservar todos
    los snapshots históricos para armar series temporales en dbt.
    """
    if df.empty:
        return 0
    df2 = df.copy()
    df2 = df2.rename(columns={"_ingested_at": "ingested_at"})

    # Asegurar todas las columnas target (las que falten -> None)
    for col in PG_COLUMNS:
        if col not in df2.columns:
            df2[col] = None

    return get_pg().upsert_dataframe(
        df2,
        table=PG_TABLE,
        columns=PG_COLUMNS,
    )


def run() -> str:
    """Pipeline completo: fetch -> transform -> dual-write (MinIO + Postgres)."""
    configure_logging()
    raw = fetch(per_page=100, page=1)
    df = transform(raw)
    key = persist(df)
    pg_rows = persist_to_postgres(df)
    log.info("coingecko.run.complete", rows=len(df), key=key, pg_rows=pg_rows)
    return key


if __name__ == "__main__":
    run()
