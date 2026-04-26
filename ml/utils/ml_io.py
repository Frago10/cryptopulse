"""
Helpers de I/O para la capa ML.

Centraliza las consultas a Postgres (leer datos de entrada, escribir
resultados) para que los scorers se concentren solo en la lógica de
modelado. Reusa `PgClient` de la capa de ingesta.
"""
from __future__ import annotations

import os
from typing import Optional

import pandas as pd

from ingestion.utils.logging_config import get_logger
from ingestion.utils.pg_client import get_pg

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Schema de los marts. dbt compone "<base>_<+schema>" -> p.ej. "analytics_marts".
# Configurable via env var para soportar distintos targets (dev / prod / ci).
# ---------------------------------------------------------------------------
MARTS_SCHEMA = os.getenv("DBT_MARTS_SCHEMA", "analytics_marts")


# =============================================================================
# Reddit sentiment
# =============================================================================
def fetch_reddit_posts(lookback_days: int = 30, only_unscored: bool = True) -> pd.DataFrame:
    """
    Lee posts de `raw.reddit_posts` para scorear con VADER.

    Args:
        lookback_days: ventana temporal (dias) desde hoy hacia atras.
        only_unscored: si es True, excluye posts que ya tienen fila en
                       `ml.reddit_sentiment` (idempotencia).
    """
    base = """
        SELECT id, subreddit, title, COALESCE(selftext, '') AS selftext, created_utc
        FROM raw.reddit_posts
        WHERE created_utc >= NOW() - (%s || ' days')::INTERVAL
    """
    if only_unscored:
        base += """
          AND NOT EXISTS (
              SELECT 1 FROM ml.reddit_sentiment s WHERE s.post_id = raw.reddit_posts.id
          )
        """
    base += " ORDER BY created_utc DESC"

    pg = get_pg()
    with pg.conn.cursor() as cur:
        cur.execute(base, (str(lookback_days),))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
    df = pd.DataFrame(rows, columns=cols)
    log.info("ml_io.reddit.fetched", rows=len(df), lookback_days=lookback_days, only_unscored=only_unscored)
    return df


# =============================================================================
# Price series (for anomaly detection)
# =============================================================================
def fetch_hourly_prices(lookback_hours: int = 24 * 30) -> pd.DataFrame:
    """
    Lee la serie horaria de `marts.fact_prices_hourly` para cada simbolo.

    Los modelos de anomalia se entrenan por-simbolo, asi que devolvemos
    todas las filas y el scorer agrupa.
    """
    sql = f"""
        SELECT
            symbol,
            event_hour,
            close::FLOAT8                     AS close,
            hour_return::FLOAT8               AS hour_return,
            hour_volume_base_delta::FLOAT8    AS volume_base,
            avg_spread::FLOAT8                AS avg_spread,
            ticks_count
        FROM {MARTS_SCHEMA}.fact_prices_hourly
        WHERE event_hour >= NOW() - (%s || ' hours')::INTERVAL
        ORDER BY symbol, event_hour
    """
    pg = get_pg()
    with pg.conn.cursor() as cur:
        cur.execute(sql, (str(lookback_hours),))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
    df = pd.DataFrame(rows, columns=cols)
    log.info("ml_io.prices.fetched", rows=len(df), lookback_hours=lookback_hours,
             symbols=df["symbol"].nunique() if not df.empty else 0)
    return df


# =============================================================================
# Writers
# =============================================================================
REDDIT_SENT_COLS = [
    "post_id", "subreddit", "created_utc",
    "compound", "pos", "neu", "neg",
    "sentiment_label", "text_length",
    "model_version",
]

PRICE_ANOM_COLS = [
    "symbol", "event_hour", "close", "hour_return", "volume_base",
    "return_zscore", "is_anomaly_zscore", "zscore_threshold",
    "iforest_score", "is_anomaly_iforest",
    "is_anomaly_consensus",
    "model_version",
]


def upsert_reddit_sentiment(df: pd.DataFrame) -> int:
    """Upsert en `ml.reddit_sentiment` con conflicto en post_id."""
    if df.empty:
        return 0
    pg = get_pg()
    update_cols = [c for c in REDDIT_SENT_COLS if c != "post_id"]
    return pg.upsert_dataframe(
        df,
        table="ml.reddit_sentiment",
        columns=REDDIT_SENT_COLS,
        conflict_cols=["post_id"],
        update_cols=update_cols,
    )


def upsert_price_anomalies(df: pd.DataFrame) -> int:
    """Upsert en `ml.price_anomalies` con conflicto en (symbol, event_hour)."""
    if df.empty:
        return 0
    pg = get_pg()
    update_cols = [c for c in PRICE_ANOM_COLS if c not in ("symbol", "event_hour")]
    return pg.upsert_dataframe(
        df,
        table="ml.price_anomalies",
        columns=PRICE_ANOM_COLS,
        conflict_cols=["symbol", "event_hour"],
        update_cols=update_cols,
    )
