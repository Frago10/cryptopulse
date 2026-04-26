-- =============================================================================
-- 04_bi_views.sql
-- Capa de abstraccion para herramientas BI (Power BI, Tableau, Metabase).
-- Ejecutable via psycopg2 desde pg_bootstrap (sin comandos meta de psql).
--
-- Filosofia:
--   * Power BI nunca consulta las tablas `analytics_marts.*` ni `ml.*`
--     directamente. Siempre via `bi.*`.
--   * Si renombramos un mart o cambiamos una columna, solo actualizamos
--     la vista — el .pbix del analista no se rompe.
--   * Las vistas son DELGADAS: joins simples + renames, sin logica pesada.
--     La logica pesada vive en dbt.
--
-- Al agregar una vista nueva, recordar:
--   1. Agregarla al pbix/queries.m como nueva tabla de Power Query.
--   2. Si introduce dimensiones nuevas, crear relaciones en el modelo PBI.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS bi;
GRANT USAGE ON SCHEMA bi TO cryptopulse;

-- -----------------------------------------------------------------------------
-- bi.v_kpi_latest
-- Una unica fila con los KPIs ejecutivos de "ahora mismo". Alimenta las
-- cards de la pagina Executive Summary.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW bi.v_kpi_latest AS
WITH last_24h AS (
    SELECT
        COUNT(DISTINCT symbol)                            AS symbols_with_ticks_24h,
        MAX(event_time)                                   AS last_tick_at,
        EXTRACT(EPOCH FROM NOW() - MAX(event_time))/60.0  AS minutes_since_last_tick
    FROM raw.ticks
    WHERE event_time >= NOW() - INTERVAL '24 hours'
),
alerts_24h AS (
    SELECT
        COUNT(*) FILTER (WHERE event_hour >= NOW() - INTERVAL '24 hours')
            AS anomaly_events_24h,
        COUNT(*) FILTER (WHERE is_anomaly_consensus
                           AND event_hour >= NOW() - INTERVAL '24 hours')
            AS anomaly_events_consensus_24h,
        MAX(severity_score) FILTER (WHERE event_hour >= NOW() - INTERVAL '24 hours')
            AS max_severity_24h
    FROM analytics_marts.mart_anomaly_alerts
),
fng_latest AS (
    SELECT
        fng_value, fng_bucket, date_day AS fng_as_of
    FROM analytics_marts.fact_sentiment_daily
    WHERE fng_value IS NOT NULL
    ORDER BY date_day DESC
    LIMIT 1
),
sentiment_24h AS (
    SELECT
        AVG(compound)::NUMERIC(6,4)  AS vader_compound_avg_24h,
        COUNT(*)                     AS reddit_posts_scored_24h
    FROM ml.reddit_sentiment
    WHERE created_utc >= NOW() - INTERVAL '24 hours'
),
market AS (
    SELECT SUM(market_cap)::NUMERIC(30,2) AS total_market_cap_tracked
    FROM (
        SELECT DISTINCT ON (coin_id) coin_id, market_cap
        FROM analytics_marts.fact_market_snapshot
        ORDER BY coin_id, snapshot_hour DESC
    ) t
)
SELECT
    l.symbols_with_ticks_24h,
    l.last_tick_at,
    ROUND(l.minutes_since_last_tick::NUMERIC, 2)  AS minutes_since_last_tick,
    a.anomaly_events_24h,
    a.anomaly_events_consensus_24h,
    a.max_severity_24h,
    f.fng_value,
    f.fng_bucket,
    f.fng_as_of,
    s.vader_compound_avg_24h,
    s.reddit_posts_scored_24h,
    m.total_market_cap_tracked,
    NOW() AS refreshed_at
FROM last_24h l
CROSS JOIN alerts_24h a
LEFT JOIN fng_latest f       ON TRUE
CROSS JOIN sentiment_24h s
CROSS JOIN market m;

COMMENT ON VIEW bi.v_kpi_latest IS
  'KPI ejecutivos last-24h + latest. Una sola fila. Alimenta cards del dashboard.';

-- -----------------------------------------------------------------------------
-- bi.v_price_hourly
-- Serie horaria de precios con nombre legible del coin. Power BI lo usa
-- para el line chart de precios y para candlestick (con visual marketplace).
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW bi.v_price_hourly AS
SELECT
    f.event_hour                                   AS ts_hour,
    f.date_key,
    f.symbol,
    COALESCE(d.coin_name, f.symbol)                AS coin_name,
    d.image_url,
    f.open::NUMERIC(20,8)                          AS price_open,
    f.high::NUMERIC(20,8)                          AS price_high,
    f.low::NUMERIC(20,8)                           AS price_low,
    f.close::NUMERIC(20,8)                         AS price_close,
    f.vwap::NUMERIC(20,8)                          AS price_vwap,
    f.hour_return::NUMERIC(10,4)                   AS hour_return_pct,
    f.ticks_count,
    f.avg_spread::NUMERIC(10,6)                    AS avg_spread
FROM analytics_marts.fact_prices_hourly f
LEFT JOIN analytics_marts.dim_coin d ON d.coin_key = f.coin_key;

COMMENT ON VIEW bi.v_price_hourly IS
  'fact_prices_hourly + nombre legible del coin. Granularidad: (symbol, hora).';

-- -----------------------------------------------------------------------------
-- bi.v_anomaly_alerts
-- Alertas listas para la page "Price Anomalies". Una fila por (symbol, hora)
-- marcada como anomalia.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW bi.v_anomaly_alerts AS
SELECT
    a.event_hour                                AS ts_hour,
    a.date_key,
    a.symbol,
    COALESCE(d.coin_name, a.coin_id, a.symbol)  AS coin_name,
    d.image_url,
    a.close::NUMERIC(20,8)                      AS price_close,
    a.hour_return::NUMERIC(10,4)                AS hour_return_pct,
    a.return_zscore,
    a.is_anomaly_zscore,
    a.is_anomaly_iforest,
    a.is_anomaly_consensus,
    CASE
        WHEN a.is_anomaly_consensus           THEN 'Consensus'
        WHEN a.is_anomaly_zscore AND a.is_anomaly_iforest THEN 'Both'
        WHEN a.is_anomaly_iforest             THEN 'IForest'
        WHEN a.is_anomaly_zscore              THEN 'Z-score'
        ELSE 'Unknown'
    END                                          AS detector_label,
    a.severity_score::NUMERIC(10,4)             AS severity,
    CASE
        WHEN a.severity_score >= 5 THEN 'Critical'
        WHEN a.severity_score >= 3 THEN 'High'
        WHEN a.severity_score >= 1 THEN 'Medium'
        ELSE 'Low'
    END                                          AS severity_bucket,
    a.market_cap_rank,
    a.fng_value,
    a.fng_bucket,
    a.reddit_mentions_day,
    a.vader_compound_avg,
    a.anomaly_model_version,
    a.detected_at
FROM analytics_marts.mart_anomaly_alerts a
LEFT JOIN analytics_marts.dim_coin d ON d.coin_id = a.coin_id;

COMMENT ON VIEW bi.v_anomaly_alerts IS
  'Alertas de anomalia + bucket de severidad para KPI cards y drill-through.';

-- -----------------------------------------------------------------------------
-- bi.v_sentiment_daily
-- Sentimiento diario (F&G + VADER agregado). Alimenta la page "Sentiment".
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW bi.v_sentiment_daily AS
WITH vader_agg AS (
    SELECT
        DATE_TRUNC('day', created_utc)::DATE           AS date_day,
        COUNT(*)                                       AS vader_posts_count,
        AVG(compound)::NUMERIC(6,4)                    AS vader_compound_avg,
        AVG(CASE WHEN sentiment_label = 'positive'
                 THEN 1.0 ELSE 0.0 END)::NUMERIC(6,4)  AS vader_pct_positive,
        AVG(CASE WHEN sentiment_label = 'negative'
                 THEN 1.0 ELSE 0.0 END)::NUMERIC(6,4)  AS vader_pct_negative
    FROM ml.reddit_sentiment
    GROUP BY 1
)
SELECT
    s.date_day,
    s.fng_value,
    s.fng_bucket,
    s.fng_score,
    s.reddit_posts_count,
    s.reddit_avg_upvote_ratio,
    s.reddit_total_score,
    v.vader_posts_count,
    v.vader_compound_avg,
    v.vader_pct_positive,
    v.vader_pct_negative
FROM analytics_marts.fact_sentiment_daily s
LEFT JOIN vader_agg v USING (date_day);

COMMENT ON VIEW bi.v_sentiment_daily IS
  'Fear&Greed + agregados VADER por dia. Granularidad: 1 fila por fecha.';

-- -----------------------------------------------------------------------------
-- bi.v_market_snapshot_latest
-- Ultimo snapshot de CoinGecko por moneda. Alimenta la tabla de overview.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW bi.v_market_snapshot_latest AS
WITH ranked AS (
    SELECT
        m.*,
        ROW_NUMBER() OVER (PARTITION BY m.coin_id ORDER BY m.snapshot_hour DESC) AS rn
    FROM analytics_marts.fact_market_snapshot m
)
SELECT
    r.coin_id,
    r.symbol,
    COALESCE(d.coin_name, r.symbol)           AS coin_name,
    d.image_url,
    r.current_price::NUMERIC(24,8)            AS price,
    r.market_cap,
    r.market_cap_rank,
    r.volume_24h,
    r.high_24h,
    r.low_24h,
    r.price_change_pct_24h::NUMERIC(12,4)     AS change_24h_pct,
    r.price_change_pct_7d::NUMERIC(12,4)      AS change_7d_pct,
    r.price_change_pct_1h::NUMERIC(12,4)      AS change_1h_pct,
    r.snapshot_hour                           AS as_of
FROM ranked r
LEFT JOIN analytics_marts.dim_coin d ON d.coin_id = r.coin_id
WHERE r.rn = 1;

COMMENT ON VIEW bi.v_market_snapshot_latest IS
  'Ultimo snapshot por moneda. Una fila por coin. Alimenta overview table.';

-- -----------------------------------------------------------------------------
-- Permisos
-- -----------------------------------------------------------------------------
GRANT SELECT ON ALL TABLES    IN SCHEMA bi TO cryptopulse;
ALTER DEFAULT PRIVILEGES IN SCHEMA bi GRANT SELECT ON TABLES TO cryptopulse;
