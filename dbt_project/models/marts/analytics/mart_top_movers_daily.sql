{{
    config(
        materialized='table',
        tags=['analytics', 'mart']
    )
}}

/*
  mart_top_movers_daily
  ---------------------
  Mart "consumo directo" para dashboards: top gainers / losers del día
  usando CoinGecko (fuente más confiable para 24h change que nuestros ticks,
  que pueden tener gaps).

  Una fila por (date_key, coin_key). Calcula:
    * last_snapshot del día
    * rank_gainer (1 = mayor subida del día)
    * rank_loser  (1 = mayor bajada del día)
    * is_top10_gainer / is_top10_loser  → flags listos para el dashboard
*/

WITH daily_last AS (
    SELECT
        date_key,
        coin_key,
        coin_id,
        symbol,
        market_cap,
        market_cap_rank,
        current_price,
        price_change_pct_24h,
        volume_24h,
        ROW_NUMBER() OVER (
            PARTITION BY date_key, coin_key
            ORDER BY snapshot_hour DESC
        ) AS rn
    FROM {{ ref('fact_market_snapshot') }}
    WHERE market_cap_rank IS NOT NULL
      AND market_cap_rank <= 200          -- solo monedas con market cap relevante
),

latest AS (
    SELECT * FROM daily_last WHERE rn = 1
),

ranked AS (
    SELECT
        l.*,
        RANK() OVER (
            PARTITION BY l.date_key
            ORDER BY l.price_change_pct_24h DESC NULLS LAST
        ) AS rank_gainer,
        RANK() OVER (
            PARTITION BY l.date_key
            ORDER BY l.price_change_pct_24h ASC NULLS LAST
        ) AS rank_loser
    FROM latest l
    WHERE l.price_change_pct_24h IS NOT NULL
)

SELECT
    date_key,
    coin_key,
    coin_id,
    symbol,
    market_cap,
    market_cap_rank,
    current_price,
    price_change_pct_24h,
    volume_24h,
    rank_gainer,
    rank_loser,
    (rank_gainer <= 10)   AS is_top10_gainer,
    (rank_loser  <= 10)   AS is_top10_loser,
    CURRENT_TIMESTAMP     AS dw_updated_at
FROM ranked
