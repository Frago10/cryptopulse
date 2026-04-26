{{
    config(
        materialized='table',
        tags=['core', 'fact']
    )
}}

/*
  fact_prices_hourly
  ------------------
  Hecho: OHLCV por moneda por hora, derivado de los ticks streaming.

  Una fila por (coin_key, event_hour).

  Agregaciones por hora:
    - OPEN  : precio del PRIMER tick de la hora (por event_time)
    - CLOSE : precio del ÚLTIMO tick de la hora
    - HIGH  : MAX(price)
    - LOW   : MIN(price)
    - VWAP  : SUM(price * volume_base) / SUM(volume_base) — promedio ponderado
    - VOLUME_BASE / VOLUME_QUOTE: último valor reportado (Binance manda acumulados 24h;
                                  tomar el último de la hora refleja la "foto" al cierre)
    - TRADES_COUNT: último valor reportado
    - AVG_SPREAD  : AVG(spread) promedio del bid-ask

  Nota: Binance el `volume_base` del ticker 24hr es CUMULATIVO de las últimas
  24 horas. Para un volumen "de la hora" real deberíamos hacer una diferencia
  contra la hora previa — lo agregamos como columna `hour_volume_delta`.

  Solo conservamos barras con >= `min_ticks_per_hour` ticks (var del proyecto).
*/

WITH ticks AS (
    SELECT
        base_asset,
        event_hour,
        event_time,
        price,
        volume_base,
        volume_quote,
        trades_count,
        spread,
        DENSE_RANK() OVER (
            PARTITION BY base_asset, event_hour
            ORDER BY event_time ASC
        )                                                      AS rk_asc,
        DENSE_RANK() OVER (
            PARTITION BY base_asset, event_hour
            ORDER BY event_time DESC
        )                                                      AS rk_desc
    FROM {{ ref('stg_ticks') }}
),

aggregated AS (
    SELECT
        base_asset                                             AS symbol,
        event_hour,
        MIN(price)                                             AS low,
        MAX(price)                                             AS high,
        COUNT(*)                                               AS ticks_count,
        SUM(price * volume_base) / NULLIF(SUM(volume_base),0)  AS vwap,
        AVG(spread)                                            AS avg_spread,
        MAX(CASE WHEN rk_asc  = 1 THEN price END)              AS open,
        MAX(CASE WHEN rk_desc = 1 THEN price END)              AS close,
        MAX(CASE WHEN rk_desc = 1 THEN volume_base END)        AS volume_base_24h,
        MAX(CASE WHEN rk_desc = 1 THEN volume_quote END)       AS volume_quote_24h,
        MAX(CASE WHEN rk_desc = 1 THEN trades_count END)       AS trades_count_24h
    FROM ticks
    GROUP BY base_asset, event_hour
    HAVING COUNT(*) >= {{ var('min_ticks_per_hour', 10) }}
),

with_deltas AS (
    SELECT
        *,
        -- Volumen "de la hora" = delta contra la hora previa (si existe)
        volume_base_24h - LAG(volume_base_24h)
            OVER (PARTITION BY symbol ORDER BY event_hour)     AS hour_volume_base_delta,
        trades_count_24h - LAG(trades_count_24h)
            OVER (PARTITION BY symbol ORDER BY event_hour)     AS hour_trades_delta,
        -- Price return hora-a-hora
        close / NULLIF(LAG(close) OVER (
            PARTITION BY symbol ORDER BY event_hour), 0) - 1   AS hour_return
    FROM aggregated
),

coin_map AS (
    -- Map desde base_asset (BTC) hacia coin_id (bitcoin) usando la dim
    SELECT
        coin_key,
        coin_id,
        UPPER(symbol) AS symbol
    FROM {{ ref('dim_coin') }}
)

SELECT
    {{ dbt_utils.generate_surrogate_key(['cm.coin_key', "TO_CHAR(d.event_hour,'YYYYMMDDHH24')"]) }}
                                                               AS price_hour_key,
    cm.coin_key,
    cm.coin_id,
    d.symbol,
    d.event_hour,
    (TO_CHAR(d.event_hour, 'YYYYMMDD'))::INT                   AS date_key,
    d.open,
    d.high,
    d.low,
    d.close,
    d.vwap,
    d.avg_spread,
    d.ticks_count,
    d.volume_base_24h,
    d.volume_quote_24h,
    d.trades_count_24h,
    d.hour_volume_base_delta,
    d.hour_trades_delta,
    d.hour_return,
    CURRENT_TIMESTAMP                                          AS dw_updated_at
FROM with_deltas d
LEFT JOIN coin_map cm ON cm.symbol = d.symbol
