{{
    config(
        materialized='table',
        tags=['analytics', 'mart']
    )
}}

/*
  mart_social_vs_price
  --------------------
  Cruza actividad social de Reddit con movimiento de precios, por día y
  por moneda. El objetivo es dar al dashboard una vista "does hype lead
  or lag price?".

  Fan-out: `fact_sentiment_daily` es una fila/día; acá explotamos la
  columna `mentions_<ticker>` en filas (date, coin) para que joinee con
  el precio por moneda.

  Señales calculadas:
    * mentions_count (del día, para esa moneda)
    * price_change_pct_24h (mismo día)
    * fng_value (contexto de mercado)
    * lead_1d_return: return del SIGUIENTE día → ¿predicen las menciones?
*/

WITH mentions_long AS (
    -- fan-out: una fila por (date, symbol) a partir de las columnas wide
    SELECT date_key, date_day, 'BTC'  AS symbol, mentions_btc  AS mentions_count,
           fng_value, fng_bucket, fng_score
    FROM {{ ref('fact_sentiment_daily') }}
    UNION ALL
    SELECT date_key, date_day, 'ETH', mentions_eth,  fng_value, fng_bucket, fng_score
    FROM {{ ref('fact_sentiment_daily') }}
    UNION ALL
    SELECT date_key, date_day, 'SOL', mentions_sol,  fng_value, fng_bucket, fng_score
    FROM {{ ref('fact_sentiment_daily') }}
    UNION ALL
    SELECT date_key, date_day, 'ADA', mentions_ada,  fng_value, fng_bucket, fng_score
    FROM {{ ref('fact_sentiment_daily') }}
    UNION ALL
    SELECT date_key, date_day, 'XRP', mentions_xrp,  fng_value, fng_bucket, fng_score
    FROM {{ ref('fact_sentiment_daily') }}
    UNION ALL
    SELECT date_key, date_day, 'DOGE', mentions_doge, fng_value, fng_bucket, fng_score
    FROM {{ ref('fact_sentiment_daily') }}
),

price_daily AS (
    -- Último snapshot por día por moneda: tiene price_change_pct_24h consolidado
    SELECT
        date_key,
        coin_key,
        coin_id,
        symbol,
        current_price,
        price_change_pct_24h,
        market_cap,
        market_cap_rank,
        ROW_NUMBER() OVER (
            PARTITION BY date_key, coin_key
            ORDER BY snapshot_hour DESC
        ) AS rn
    FROM {{ ref('fact_market_snapshot') }}
),

price_latest AS (
    SELECT * FROM price_daily WHERE rn = 1
),

joined AS (
    SELECT
        m.date_key,
        m.date_day,
        p.coin_key,
        p.coin_id,
        m.symbol,
        m.mentions_count,
        p.current_price,
        p.price_change_pct_24h,
        p.market_cap,
        p.market_cap_rank,
        m.fng_value,
        m.fng_bucket,
        m.fng_score
    FROM mentions_long m
    LEFT JOIN price_latest p
      ON p.date_key = m.date_key
     AND p.symbol   = m.symbol
),

with_lead AS (
    SELECT
        *,
        LEAD(price_change_pct_24h) OVER (
            PARTITION BY symbol ORDER BY date_key
        ) AS lead_1d_return
    FROM joined
)

SELECT
    date_key,
    date_day,
    coin_key,
    coin_id,
    symbol,
    mentions_count,
    current_price,
    price_change_pct_24h,
    lead_1d_return,
    market_cap,
    market_cap_rank,
    fng_value,
    fng_bucket,
    fng_score,
    CURRENT_TIMESTAMP AS dw_updated_at
FROM with_lead
