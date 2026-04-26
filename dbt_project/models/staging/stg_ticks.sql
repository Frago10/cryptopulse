{{
    config(
        materialized='view',
        tags=['streaming', 'staging']
    )
}}

/*
  stg_ticks
  ---------
  Normaliza los ticks crudos de Binance:
    * Separa base y quote del símbolo (BTCUSDT -> BTC / USDT)
    * Bucketea el event_time a minuto y hora (para agregaciones downstream)
    * Filtra precios no positivos y volúmenes negativos (ruido de conexión)

  Materializado como VIEW — los ticks tienen alto volumen pero las queries
  analíticas bajan al mart agregado. Una view aquí evita duplicar el storage.
*/

WITH source AS (
    SELECT
        symbol,
        event_time,
        price,
        price_change_pct,
        volume_base,
        volume_quote,
        trades_count,
        bid,
        ask,
        ingested_at
    FROM {{ source('raw', 'ticks') }}
    WHERE
        price > 0
        AND volume_base >= 0
        AND symbol IS NOT NULL
),

enriched AS (
    SELECT
        symbol,
        -- USDT es el quote en todos nuestros símbolos; si cambia, regex aquí
        CASE
            WHEN symbol LIKE '%USDT' THEN LEFT(symbol, LENGTH(symbol) - 4)
            ELSE symbol
        END                                 AS base_asset,
        CASE
            WHEN symbol LIKE '%USDT' THEN 'USDT'
            ELSE NULL
        END                                 AS quote_asset,

        event_time,
        DATE_TRUNC('minute', event_time)    AS event_minute,
        DATE_TRUNC('hour',   event_time)    AS event_hour,
        DATE_TRUNC('day',    event_time)    AS event_date,

        price,
        price_change_pct,
        volume_base,
        volume_quote,
        trades_count,
        bid,
        ask,
        (ask - bid)                         AS spread,
        CASE
            WHEN bid > 0 THEN (ask - bid) / bid * 100
            ELSE NULL
        END                                 AS spread_pct,
        ingested_at
    FROM source
)

SELECT * FROM enriched
