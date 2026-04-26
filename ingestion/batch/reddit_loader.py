"""
Reddit loader — subreddits relacionados con cripto.

Dos modos de fetch, seleccionados automáticamente:

  1. PRAW (preferido, requiere credenciales en .env):
         REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT
     Ventajas: rate limit alto (60 req/min autenticado), acceso estable.
     Cómo obtenerlas (2 min): https://www.reddit.com/prefs/apps
        -> "create another app..." type=script  redirect=http://localhost:8080

  2. Modo PÚBLICO (fallback, sin credenciales):
     Consume el endpoint JSON anónimo https://www.reddit.com/r/<sub>/new.json
     Ventajas: funciona sin configurar nada.
     Limitaciones: rate limit más bajo (~60 req/min por IP), y Reddit exige
     un User-Agent "único" para no bloquear.
     Para nuestro volumen (4 subreddits * 50 posts cada run horario) alcanza
     y sobra.

El caller solo llama `fetch()` — el loader decide el modo.

Subreddits rastreados:
  r/cryptocurrency, r/bitcoin, r/ethereum, r/solana

Salida normalizada (ambos modos producen el mismo shape de dict):
  id, subreddit, title, selftext, author, score, upvote_ratio, num_comments,
  created_utc, url, is_self, over_18, permalink
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Iterable

import pandas as pd
import requests

from ingestion.utils.config import settings
from ingestion.utils.logging_config import configure_logging, get_logger
from ingestion.utils.minio_client import get_minio
from ingestion.utils.pg_client import get_pg

log = get_logger(__name__)

SOURCE = "reddit"
DATASET = "posts"

DEFAULT_SUBREDDITS = ("cryptocurrency", "bitcoin", "ethereum", "solana")

PG_TABLE = "raw.reddit_posts"
PG_COLUMNS = [
    "id", "subreddit", "title", "selftext", "author",
    "score", "upvote_ratio", "num_comments", "created_utc",
    "url", "is_self", "over_18", "permalink", "ingested_at",
]

# Endpoint JSON público (no requiere auth)
PUBLIC_ENDPOINT = "https://www.reddit.com/r/{sub}/new.json"
# Pequeño delay entre subreddits en modo público para respetar rate limits
PUBLIC_DELAY_SECONDS = 1.0


# -----------------------------------------------------------------
# Selector de modo
# -----------------------------------------------------------------
def _has_reddit_credentials() -> bool:
    """Detecta si hay credenciales reales (no vacías ni placeholder)."""
    cid = (settings.REDDIT_CLIENT_ID or "").strip()
    csec = (settings.REDDIT_CLIENT_SECRET or "").strip()
    if not cid or not csec:
        return False
    placeholders = {"REPLACE_WITH_YOUR_CLIENT_ID", "REPLACE_WITH_YOUR_CLIENT_SECRET",
                    "tu_client_id", "tu_client_secret", "your_client_id"}
    return cid not in placeholders and csec not in placeholders


# -----------------------------------------------------------------
# Modo 1: PRAW (autenticado)
# -----------------------------------------------------------------
def _fetch_praw(subreddits: Iterable[str], limit: int) -> list[dict]:
    import praw  # type: ignore

    reddit = praw.Reddit(
        client_id=settings.REDDIT_CLIENT_ID,
        client_secret=settings.REDDIT_CLIENT_SECRET,
        user_agent=settings.REDDIT_USER_AGENT,
    )
    rows: list[dict] = []
    for name in subreddits:
        log.info("reddit.praw.subreddit", subreddit=name, limit=limit)
        try:
            for post in reddit.subreddit(name).new(limit=limit):
                rows.append({
                    "id": post.id,
                    "subreddit": name,
                    "title": post.title,
                    "selftext": (post.selftext or "")[:2000],
                    "author": str(post.author) if post.author else None,
                    "score": int(post.score),
                    "upvote_ratio": float(post.upvote_ratio),
                    "num_comments": int(post.num_comments),
                    "created_utc": datetime.fromtimestamp(post.created_utc, tz=timezone.utc),
                    "url": post.url,
                    "is_self": bool(post.is_self),
                    "over_18": bool(post.over_18),
                    "permalink": f"https://reddit.com{post.permalink}",
                })
        except Exception as exc:
            log.error("reddit.praw.error", subreddit=name, error=str(exc))
    return rows


# -----------------------------------------------------------------
# Modo 2: HTTP público (sin credenciales)
# -----------------------------------------------------------------
def _fetch_public(subreddits: Iterable[str], limit: int) -> list[dict]:
    """
    Llama al endpoint JSON anónimo. Reddit exige un User-Agent custom —
    usamos el configurado en .env (o un default razonable).
    """
    ua = settings.REDDIT_USER_AGENT or "cryptopulse/0.1 (public-mode)"
    headers = {"User-Agent": ua, "Accept": "application/json"}

    rows: list[dict] = []
    for i, name in enumerate(subreddits):
        url = PUBLIC_ENDPOINT.format(sub=name)
        log.info("reddit.public.subreddit", subreddit=name, limit=limit, url=url)
        try:
            resp = requests.get(url, headers=headers, params={"limit": limit}, timeout=20)
            # Reddit a veces devuelve 429 si se tiraron muchas consultas seguidas
            if resp.status_code == 429:
                log.warning("reddit.public.rate_limited", subreddit=name,
                            retry_after=resp.headers.get("Retry-After"))
                time.sleep(5)
                resp = requests.get(url, headers=headers, params={"limit": limit}, timeout=20)
            resp.raise_for_status()
            payload = resp.json()
            children = payload.get("data", {}).get("children", [])
            for child in children:
                d = child.get("data", {})
                try:
                    rows.append({
                        "id": d["id"],
                        "subreddit": name,
                        "title": d.get("title", ""),
                        "selftext": (d.get("selftext") or "")[:2000],
                        "author": d.get("author"),
                        "score": int(d.get("score") or 0),
                        "upvote_ratio": float(d.get("upvote_ratio") or 0.0),
                        "num_comments": int(d.get("num_comments") or 0),
                        "created_utc": datetime.fromtimestamp(
                            float(d["created_utc"]), tz=timezone.utc
                        ),
                        "url": d.get("url"),
                        "is_self": bool(d.get("is_self")),
                        "over_18": bool(d.get("over_18")),
                        "permalink": f"https://reddit.com{d.get('permalink', '')}",
                    })
                except KeyError as exc:
                    log.warning("reddit.public.skip_post", missing_field=str(exc))
        except Exception as exc:
            log.error("reddit.public.error", subreddit=name, error=str(exc))

        # Delay entre subreddits para ser buen ciudadano
        if i < len(list(subreddits)) - 1:
            time.sleep(PUBLIC_DELAY_SECONDS)

    return rows


# -----------------------------------------------------------------
# API pública del loader
# -----------------------------------------------------------------
def fetch(subreddits: Iterable[str] = DEFAULT_SUBREDDITS, limit: int = 50) -> list[dict]:
    """
    Para cada subreddit trae las últimas `limit` publicaciones (new).
    Selecciona modo PRAW si hay credenciales válidas; si no, modo público.
    """
    # Materializar por si vino un iterador que solo se puede consumir una vez
    subs = list(subreddits)
    mode = "praw" if _has_reddit_credentials() else "public"
    log.info("reddit.fetch.start", mode=mode, subreddits=subs, limit=limit)

    if mode == "praw":
        rows = _fetch_praw(subs, limit)
    else:
        rows = _fetch_public(subs, limit)

    log.info("reddit.fetch.ok", mode=mode, total=len(rows))
    return rows


def transform(raw: list[dict]) -> pd.DataFrame:
    if not raw:
        return pd.DataFrame()
    df = pd.DataFrame(raw)
    df["_ingested_at"] = datetime.now(timezone.utc)
    df["_source"] = SOURCE
    df["_dataset"] = DATASET
    return df


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
    Upsert en raw.reddit_posts. La PK es `id` (post id de Reddit).
    Cuando un post se re-fetcha actualizamos score/upvote_ratio/num_comments
    porque cambian con el tiempo.
    """
    if df.empty:
        return 0
    df2 = df.copy().rename(columns={"_ingested_at": "ingested_at"})
    for col in PG_COLUMNS:
        if col not in df2.columns:
            df2[col] = None

    return get_pg().upsert_dataframe(
        df2,
        table=PG_TABLE,
        columns=PG_COLUMNS,
        conflict_cols=["id"],
        update_cols=["score", "upvote_ratio", "num_comments", "ingested_at"],
    )


def run() -> str:
    configure_logging()
    raw = fetch()
    df = transform(raw)
    key = persist(df)
    pg_rows = persist_to_postgres(df)
    log.info("reddit.run.complete", rows=len(df), key=key, pg_rows=pg_rows)
    return key


if __name__ == "__main__":
    run()
