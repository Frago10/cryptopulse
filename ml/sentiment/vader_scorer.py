"""
VADER sentiment scoring sobre posts de Reddit.

¿Por qué VADER y no un LLM?
  * Es rule-based + lexicon → 100% local, cero coste, latencia irrisoria.
  * Entrenado específicamente para texto de redes sociales (slang, emojis,
    signos de exclamación, intensificadores). Para crypto-Twitter/Reddit es
    sorprendentemente competitivo con modelos pesados.
  * Output determinista — ideal para tests y reproducibilidad.

Flujo:
  1. Lee posts de `raw.reddit_posts` de los últimos N días que AÚN no
     tengan fila en `ml.reddit_sentiment` (idempotente).
  2. Scorea title + selftext concatenados.
  3. Upserts en `ml.reddit_sentiment` (PK: post_id).

Uso:
    python -m ml.sentiment.vader_scorer                  # lookback 30d
    python -m ml.sentiment.vader_scorer --lookback-days 7
    python -m ml.sentiment.vader_scorer --rescore-all    # re-scorea todo
"""
from __future__ import annotations

import argparse
import sys
from typing import Dict

import pandas as pd

from ingestion.utils.logging_config import configure_logging, get_logger
from ml.utils.ml_io import fetch_reddit_posts, upsert_reddit_sentiment

log = get_logger(__name__)

MODEL_VERSION = "vader-3.3.2"

# Umbrales estándar del paper de VADER (Hutto & Gilbert 2014):
#   positive:  compound >=  0.05
#   negative:  compound <= -0.05
#   neutral:   en el medio
POSITIVE_THRESHOLD = 0.05
NEGATIVE_THRESHOLD = -0.05


def _load_analyzer():
    """Lazy import para que el módulo se pueda importar sin instalar vader."""
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "Falta vaderSentiment. Instalalo con: pip install vaderSentiment"
        ) from e
    return SentimentIntensityAnalyzer()


def _label(compound: float) -> str:
    if compound >= POSITIVE_THRESHOLD:
        return "positive"
    if compound <= NEGATIVE_THRESHOLD:
        return "negative"
    return "neutral"


def score_posts(df: pd.DataFrame) -> pd.DataFrame:
    """
    Toma el DataFrame devuelto por `fetch_reddit_posts` y devuelve uno listo
    para persistir en `ml.reddit_sentiment`.
    """
    if df.empty:
        return pd.DataFrame(columns=[
            "post_id", "subreddit", "created_utc",
            "compound", "pos", "neu", "neg",
            "sentiment_label", "text_length", "model_version",
        ])

    analyzer = _load_analyzer()

    # Texto combinado: título + body (con body truncado a 4000 chars para proteger memoria)
    title = df["title"].fillna("").astype(str)
    body = df["selftext"].fillna("").astype(str).str.slice(0, 4000)
    combined = (title + "\n\n" + body).str.strip()

    scores: list[Dict[str, float]] = [analyzer.polarity_scores(t) for t in combined]
    scores_df = pd.DataFrame(scores)  # columns: neg, neu, pos, compound

    out = pd.DataFrame({
        "post_id":         df["id"].astype(str),
        "subreddit":       df["subreddit"].astype(str),
        "created_utc":     df["created_utc"],
        "compound":        scores_df["compound"].astype(float),
        "pos":             scores_df["pos"].astype(float),
        "neu":             scores_df["neu"].astype(float),
        "neg":             scores_df["neg"].astype(float),
        "sentiment_label": scores_df["compound"].apply(_label),
        "text_length":     combined.str.len().astype(int),
        "model_version":   MODEL_VERSION,
    })
    return out


def run(lookback_days: int = 30, rescore_all: bool = False) -> int:
    """Entrypoint del script. Devuelve cantidad de filas escritas."""
    configure_logging()

    df_posts = fetch_reddit_posts(
        lookback_days=lookback_days,
        only_unscored=not rescore_all,
    )
    if df_posts.empty:
        log.info("vader.nothing_to_score", lookback_days=lookback_days)
        return 0

    log.info("vader.scoring", posts=len(df_posts))
    df_out = score_posts(df_posts)

    # Resumen rápido por clase — útil para detectar drift de una corrida a otra
    summary = df_out["sentiment_label"].value_counts().to_dict()
    log.info("vader.summary", **summary, total=len(df_out),
             mean_compound=float(df_out["compound"].mean()))

    written = upsert_reddit_sentiment(df_out)
    log.info("vader.written", rows=written)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VADER sentiment scorer for Reddit posts")
    parser.add_argument("--lookback-days", type=int, default=30,
                        help="Ventana temporal en días hacia atrás (default: 30)")
    parser.add_argument("--rescore-all", action="store_true",
                        help="Re-scorea también posts que ya estaban en ml.reddit_sentiment")
    args = parser.parse_args(argv)

    run(lookback_days=args.lookback_days, rescore_all=args.rescore_all)
    return 0


if __name__ == "__main__":
    sys.exit(main())
