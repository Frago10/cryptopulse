{{
    config(
        materialized='view',
        tags=['staging', 'ml']
    )
}}

/*
  stg_reddit_sentiment
  --------------------
  Staging view sobre `ml.reddit_sentiment`. Normaliza nombres y agrega
  buckets útiles para agregaciones diarias.
*/

SELECT
    post_id,
    subreddit,
    created_utc,
    created_utc::DATE                   AS created_date,
    DATE_TRUNC('hour', created_utc)     AS created_hour,
    compound,
    pos,
    neu,
    neg,
    sentiment_label,
    -- Bucket numérico para promediar luego
    CASE sentiment_label
        WHEN 'positive' THEN  1
        WHEN 'negative' THEN -1
        ELSE 0
    END                                 AS sentiment_score,
    text_length,
    model_version,
    scored_at
FROM {{ source('ml', 'reddit_sentiment') }}
