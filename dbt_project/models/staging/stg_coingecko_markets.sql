{{
    config(
        materialized='view',
        tags=['batch', 'staging']
    )
}}

/*
  stg_coingecko_markets
  ---------------------
  Versión limpia del snapshot CoinGecko:
    * Renombra campos largos a algo legible
    * Deja el precio, market cap y volúmenes como NUMERIC
    * Agrega `snapshot_hour` para alinear con stg_ticks en gold

  Cada `ingested_at` representa un snapshot completo del top 100 por market cap.
*/

WITH source AS (
    SELECT
        id                                                AS coin_id,
        UPPER(symbol)                                     AS symbol,
        name                                              AS coin_name,
        image                                             AS image_url,

        current_price,
        market_cap,
        market_cap_rank,
        fully_diluted_valuation                           AS fdv,
        total_volume                                      AS volume_24h,

        high_24h,
        low_24h,
        price_change_24h,
        price_change_percentage_24h                       AS price_change_pct_24h,
        price_change_percentage_1h_in_currency            AS price_change_pct_1h,
        price_change_percentage_7d_in_currency            AS price_change_pct_7d,

        market_cap_change_24h,
        market_cap_change_percentage_24h                  AS market_cap_change_pct_24h,

        circulating_supply,
        total_supply,
        max_supply,

        ath,
        ath_change_percentage                             AS ath_change_pct,
        ath_date,
        atl,
        atl_change_percentage                             AS atl_change_pct,
        atl_date,

        last_updated,
        ingested_at,
        DATE_TRUNC('hour', ingested_at)                   AS snapshot_hour,
        DATE_TRUNC('day',  ingested_at)                   AS snapshot_date
    FROM {{ source('raw', 'coingecko_markets') }}
    WHERE current_price IS NOT NULL
)

SELECT * FROM source
