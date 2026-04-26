{{
    config(
        materialized='view',
        tags=['batch', 'staging']
    )
}}

/*
  stg_reddit_posts
  ----------------
  Normalización de posts de Reddit:
    * Lowercase subreddit (consistencia)
    * Trunca selftext a 500 chars para previews en el dashboard
    * Detecta menciones de tickers (BTC, ETH, SOL, ...) con regex
    * Agrega `created_hour` y `created_date` para joins temporales

  El análisis de sentimiento VADER vive en la capa ML (Fase 5) — aquí solo
  preparamos el texto.
*/

WITH source AS (
    SELECT
        id,
        LOWER(subreddit)                                 AS subreddit,
        title,
        selftext,
        LEFT(COALESCE(selftext, ''), 500)                AS selftext_preview,
        author,
        score,
        upvote_ratio,
        num_comments,
        created_utc,
        url,
        is_self,
        over_18,
        permalink,
        ingested_at,
        DATE_TRUNC('hour', created_utc)                  AS created_hour,
        DATE_TRUNC('day',  created_utc)                  AS created_date,

        -- Concatenar título + texto para análisis downstream
        CONCAT(title, ' ', COALESCE(selftext, ''))       AS full_text
    FROM {{ source('raw', 'reddit_posts') }}
    WHERE title IS NOT NULL
      AND NOT over_18
),

tagged AS (
    SELECT
        *,
        -- Detección ultra simple de menciones por regex case-insensitive
        (full_text ~* '\mBTC\M|\mBITCOIN\M')              AS mentions_btc,
        (full_text ~* '\mETH\M|\mETHEREUM\M')             AS mentions_eth,
        (full_text ~* '\mSOL\M|\mSOLANA\M')               AS mentions_sol,
        (full_text ~* '\mADA\M|\mCARDANO\M')              AS mentions_ada,
        (full_text ~* '\mXRP\M|\mRIPPLE\M')               AS mentions_xrp,
        (full_text ~* '\mDOGE\M|\mDOGECOIN\M')            AS mentions_doge
    FROM source
)

SELECT * FROM tagged
