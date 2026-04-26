{{
    config(
        materialized='view',
        tags=['batch', 'staging']
    )
}}

/*
  stg_fear_greed
  --------------
  Normaliza el Fear & Greed Index de alternative.me:
    * Deja solo el registro más reciente por día (el endpoint a veces repite)
    * Mapea el `value` a un score normalizado [-1, 1] útil para ML
    * Agrega categoría explícita (fear_zone / neutral_zone / greed_zone)
*/

WITH latest_per_day AS (
    SELECT
        DATE_TRUNC('day', index_date)           AS index_date,
        value,
        category                                 AS raw_category,
        ingested_at,
        ROW_NUMBER() OVER (
            PARTITION BY DATE_TRUNC('day', index_date)
            ORDER BY ingested_at DESC
        )                                        AS rn
    FROM {{ source('raw', 'fear_greed_index') }}
),

deduped AS (
    SELECT
        index_date,
        value,
        raw_category,
        ingested_at
    FROM latest_per_day
    WHERE rn = 1
),

enriched AS (
    SELECT
        index_date,
        value,
        LOWER(raw_category)                              AS category,
        -- Mapa custom por bucket (más claro que el que devuelve la API)
        CASE
            WHEN value <= 24 THEN 'extreme_fear'
            WHEN value <= 44 THEN 'fear'
            WHEN value <= 54 THEN 'neutral'
            WHEN value <= 74 THEN 'greed'
            ELSE 'extreme_greed'
        END                                              AS sentiment_bucket,
        -- Normalización a [-1, 1]: 0 = extreme_fear, 100 = extreme_greed
        ROUND(((value::NUMERIC - 50) / 50.0)::numeric, 4) AS sentiment_score,
        ingested_at
    FROM deduped
)

SELECT * FROM enriched
