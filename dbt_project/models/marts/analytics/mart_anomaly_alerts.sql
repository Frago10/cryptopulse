{{
    config(
        materialized='table',
        tags=['analytics', 'mart', 'ml']
    )
}}

/*
  mart_anomaly_alerts
  -------------------
  Mart de "alertas" listas para el dashboard y para Telegram (Fase 10).

  Toma cada hora anómala por símbolo y la enriquece con contexto:
    * Precio OHLC + return + volumen de la hora              (fact_prices_hourly)
    * Market cap rank al momento                              (fact_market_snapshot: último snapshot del día)
    * Fear & Greed del día + bucket                           (fact_sentiment_daily)
    * Resumen de Reddit del mismo día:
        - mentions del ticker (BTC / ETH / ...)
        - compound MEDIO de los posts con menciones
        - % de posts positivos / negativos

  Granularidad: una fila por (symbol, event_hour) solo para horas flaggeadas
  por al menos UN detector (is_anomaly_any = TRUE).

  Uso típico:
    - Dashboard: filtrar is_anomaly_consensus = TRUE para alertas high-precision
    - Telegram: mandar cuando is_anomaly_consensus = TRUE AND |hour_return| > X%
*/

WITH anomalies AS (
    SELECT *
    FROM {{ ref('stg_price_anomalies') }}
    WHERE is_anomaly_any = TRUE
),

prices AS (
    SELECT
        coin_key, coin_id, symbol, event_hour,
        open, high, low, close, vwap, ticks_count,
        hour_return, hour_volume_base_delta, avg_spread
    FROM {{ ref('fact_prices_hourly') }}
),

market_daily AS (
    -- Último snapshot del día por moneda
    SELECT
        coin_key,
        symbol,
        date_key,
        market_cap,
        market_cap_rank,
        price_change_pct_24h,
        ROW_NUMBER() OVER (
            PARTITION BY coin_key, date_key ORDER BY snapshot_hour DESC
        ) AS rn
    FROM {{ ref('fact_market_snapshot') }}
),

market_latest AS (
    SELECT * FROM market_daily WHERE rn = 1
),

sentiment_daily AS (
    SELECT
        date_key,
        date_day,
        fng_value,
        fng_bucket,
        mentions_btc, mentions_eth, mentions_sol,
        mentions_ada, mentions_xrp, mentions_doge
    FROM {{ ref('fact_sentiment_daily') }}
),

-- Promedio diario de sentiment VADER por subreddit (todos juntos aquí —
-- para segmentar por coin se usaría una relación post↔ticker, que está
-- en stg_reddit_posts.mentions_*. Para simplicidad tomamos el promedio global
-- del día, que es un proxy razonable del "mood del mercado cripto".)
vader_daily AS (
    SELECT
        created_date                                       AS date_day,
        (TO_CHAR(created_date, 'YYYYMMDD'))::INT           AS date_key,
        COUNT(*)                                           AS reddit_scored_count,
        AVG(compound)::NUMERIC(8,4)                        AS vader_compound_avg,
        AVG(CASE WHEN sentiment_label = 'positive' THEN 1.0 ELSE 0.0 END)::NUMERIC(6,4)
                                                           AS vader_pct_positive,
        AVG(CASE WHEN sentiment_label = 'negative' THEN 1.0 ELSE 0.0 END)::NUMERIC(6,4)
                                                           AS vader_pct_negative
    FROM {{ ref('stg_reddit_sentiment') }}
    GROUP BY created_date
)

SELECT
    -- identifiers
    a.symbol,
    a.event_hour,
    a.date_key,
    p.coin_key,
    p.coin_id,

    -- price context
    p.open,
    p.high,
    p.low,
    p.close,
    p.vwap,
    p.hour_return,
    p.hour_volume_base_delta,
    p.avg_spread,
    p.ticks_count,

    -- anomaly signals
    a.return_zscore,
    a.zscore_threshold,
    a.is_anomaly_zscore,
    a.iforest_score,
    a.is_anomaly_iforest,
    a.is_anomaly_consensus,

    -- severity (entre más fuerte, más severo; para ordenar alertas)
    ABS(COALESCE(a.return_zscore, 0))                     AS severity_score,

    -- market context (latest snapshot del día)
    m.market_cap,
    m.market_cap_rank,
    m.price_change_pct_24h,

    -- sentiment context (del día)
    s.fng_value,
    s.fng_bucket,
    CASE a.symbol
        WHEN 'BTC'  THEN s.mentions_btc
        WHEN 'ETH'  THEN s.mentions_eth
        WHEN 'SOL'  THEN s.mentions_sol
        WHEN 'ADA'  THEN s.mentions_ada
        WHEN 'XRP'  THEN s.mentions_xrp
        WHEN 'DOGE' THEN s.mentions_doge
        ELSE 0
    END                                                   AS reddit_mentions_day,
    v.reddit_scored_count,
    v.vader_compound_avg,
    v.vader_pct_positive,
    v.vader_pct_negative,

    -- meta
    a.model_version                                        AS anomaly_model_version,
    a.detected_at,
    CURRENT_TIMESTAMP                                      AS dw_updated_at

FROM anomalies a
LEFT JOIN prices          p ON p.symbol   = a.symbol AND p.event_hour = a.event_hour
LEFT JOIN market_latest   m ON m.symbol   = a.symbol AND m.date_key   = a.date_key
LEFT JOIN sentiment_daily s ON s.date_key = a.date_key
LEFT JOIN vader_daily     v ON v.date_key = a.date_key
