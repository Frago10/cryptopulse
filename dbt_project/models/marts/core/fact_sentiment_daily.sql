{{
    config(
        materialized='table',
        tags=['core', 'fact']
    )
}}

/*
  fact_sentiment_daily
  --------------------
  Hecho: sentiment agregado por día. Combina dos fuentes:

    * Fear & Greed Index (1 valor global por día, no por moneda)
    * Reddit: agregados sociales del día por subreddit + menciones por ticker

  Granularidad: una fila por DÍA (no por moneda). Para cruzar con
  precios por moneda, hacemos fan-out en `mart_social_vs_price`.

  Análisis VADER de sentiment viene en Fase 5 (ML) y se incorpora
  a este hecho como columna adicional cuando esté listo.
*/

WITH fng AS (
    SELECT
        DATE_TRUNC('day', index_date)::DATE   AS date_day,
        value                                 AS fng_value,
        category                              AS fng_category,
        sentiment_bucket                      AS fng_bucket,
        sentiment_score                       AS fng_score
    FROM {{ ref('stg_fear_greed') }}
),

reddit_daily AS (
    SELECT
        created_date::DATE                    AS date_day,
        COUNT(*)                              AS reddit_posts_count,
        COUNT(DISTINCT author)                AS reddit_unique_authors,
        SUM(score)                            AS reddit_total_score,
        AVG(score)::NUMERIC(12,2)             AS reddit_avg_score,
        AVG(upvote_ratio)::NUMERIC(6,4)       AS reddit_avg_upvote_ratio,
        SUM(num_comments)                     AS reddit_total_comments,
        -- Menciones por ticker (para el fan-out en marts)
        SUM(CASE WHEN mentions_btc  THEN 1 ELSE 0 END) AS mentions_btc,
        SUM(CASE WHEN mentions_eth  THEN 1 ELSE 0 END) AS mentions_eth,
        SUM(CASE WHEN mentions_sol  THEN 1 ELSE 0 END) AS mentions_sol,
        SUM(CASE WHEN mentions_ada  THEN 1 ELSE 0 END) AS mentions_ada,
        SUM(CASE WHEN mentions_xrp  THEN 1 ELSE 0 END) AS mentions_xrp,
        SUM(CASE WHEN mentions_doge THEN 1 ELSE 0 END) AS mentions_doge
    FROM {{ ref('stg_reddit_posts') }}
    GROUP BY created_date::DATE
),

-- Union the two date domains to make sure we keep days with only one source
all_dates AS (
    SELECT date_day FROM fng
    UNION
    SELECT date_day FROM reddit_daily
)

SELECT
    (TO_CHAR(ad.date_day, 'YYYYMMDD'))::INT                       AS date_key,
    ad.date_day,
    f.fng_value,
    f.fng_category,
    f.fng_bucket,
    f.fng_score,
    COALESCE(r.reddit_posts_count, 0)                             AS reddit_posts_count,
    COALESCE(r.reddit_unique_authors, 0)                          AS reddit_unique_authors,
    COALESCE(r.reddit_total_score, 0)                             AS reddit_total_score,
    r.reddit_avg_score,
    r.reddit_avg_upvote_ratio,
    COALESCE(r.reddit_total_comments, 0)                          AS reddit_total_comments,
    COALESCE(r.mentions_btc,  0)                                  AS mentions_btc,
    COALESCE(r.mentions_eth,  0)                                  AS mentions_eth,
    COALESCE(r.mentions_sol,  0)                                  AS mentions_sol,
    COALESCE(r.mentions_ada,  0)                                  AS mentions_ada,
    COALESCE(r.mentions_xrp,  0)                                  AS mentions_xrp,
    COALESCE(r.mentions_doge, 0)                                  AS mentions_doge,
    CURRENT_TIMESTAMP                                             AS dw_updated_at
FROM all_dates ad
LEFT JOIN fng            f ON f.date_day = ad.date_day
LEFT JOIN reddit_daily   r ON r.date_day = ad.date_day
