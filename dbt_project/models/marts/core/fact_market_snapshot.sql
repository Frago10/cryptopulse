{{
    config(
        materialized='table',
        tags=['core', 'fact']
    )
}}

/*
  fact_market_snapshot
  --------------------
  Hecho: snapshots horarios de CoinGecko por moneda.

  Una fila por (coin_key, snapshot_hour). Si el loader corrió más de una vez
  en la misma hora, conservamos el snapshot MÁS reciente para no duplicar.

  Contiene KPIs que no vienen en Binance: market_cap, rank, fdv, ath/atl,
  cambio % 1h/24h/7d — son el corazón del dashboard de mercado.
*/

WITH dedup AS (
    SELECT
        coin_id,
        symbol,
        snapshot_hour,
        current_price,
        market_cap,
        market_cap_rank,
        fdv,
        volume_24h,
        high_24h,
        low_24h,
        price_change_24h,
        price_change_pct_1h,
        price_change_pct_24h,
        price_change_pct_7d,
        market_cap_change_24h,
        market_cap_change_pct_24h,
        circulating_supply,
        total_supply,
        max_supply,
        ath,
        ath_change_pct,
        ath_date,
        atl,
        atl_change_pct,
        atl_date,
        ingested_at,
        ROW_NUMBER() OVER (
            PARTITION BY coin_id, snapshot_hour
            ORDER BY ingested_at DESC
        ) AS rn
    FROM {{ ref('stg_coingecko_markets') }}
),

latest_per_hour AS (
    SELECT * FROM dedup WHERE rn = 1
),

coin_map AS (
    SELECT coin_key, coin_id FROM {{ ref('dim_coin') }}
)

SELECT
    {{ dbt_utils.generate_surrogate_key(['cm.coin_key', "TO_CHAR(l.snapshot_hour,'YYYYMMDDHH24')"]) }}
                                                        AS market_snapshot_key,
    cm.coin_key,
    l.coin_id,
    l.symbol,
    l.snapshot_hour,
    (TO_CHAR(l.snapshot_hour, 'YYYYMMDD'))::INT         AS date_key,
    l.current_price,
    l.market_cap,
    l.market_cap_rank,
    l.fdv,
    l.volume_24h,
    l.high_24h,
    l.low_24h,
    l.price_change_24h,
    l.price_change_pct_1h,
    l.price_change_pct_24h,
    l.price_change_pct_7d,
    l.market_cap_change_24h,
    l.market_cap_change_pct_24h,
    l.circulating_supply,
    l.total_supply,
    l.max_supply,
    l.ath,
    l.ath_change_pct,
    l.ath_date,
    l.atl,
    l.atl_change_pct,
    l.atl_date,
    CURRENT_TIMESTAMP                                   AS dw_updated_at
FROM latest_per_hour l
LEFT JOIN coin_map cm ON cm.coin_id = l.coin_id
