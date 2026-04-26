-- =============================================================================
-- ML outputs — tablas que alimenta la Fase 5 (anomalías + sentimiento).
-- Ejecutable via psycopg2 (sin comandos meta de psql).
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS ml;

-- ---- Reddit sentiment (VADER) ------------------------------------------------
-- Una fila por post_id. Si el post se re-scorea (p.ej. porque cambió el texto),
-- hacemos UPSERT sobre post_id.
CREATE TABLE IF NOT EXISTS ml.reddit_sentiment (
    post_id          TEXT        PRIMARY KEY,
    subreddit        TEXT        NOT NULL,
    created_utc      TIMESTAMPTZ NOT NULL,
    compound         REAL        NOT NULL,   -- [-1, 1]
    pos              REAL        NOT NULL,   -- [0, 1]
    neu              REAL        NOT NULL,   -- [0, 1]
    neg              REAL        NOT NULL,   -- [0, 1]
    sentiment_label  TEXT        NOT NULL,   -- positive | neutral | negative
    text_length      INTEGER     NOT NULL,
    model_version    TEXT        NOT NULL DEFAULT 'vader-3.3.2',
    scored_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_reddit_sent_created ON ml.reddit_sentiment (created_utc DESC);
CREATE INDEX IF NOT EXISTS idx_reddit_sent_subreddit ON ml.reddit_sentiment (subreddit);

-- ---- Price anomalies (rolling z-score + Isolation Forest) --------------------
-- Una fila por (symbol, event_hour). Los dos detectores viven en la misma
-- tabla: útil para comparar señales y para entrenar ensembles más adelante.
CREATE TABLE IF NOT EXISTS ml.price_anomalies (
    symbol               TEXT         NOT NULL,
    event_hour           TIMESTAMPTZ  NOT NULL,
    close                NUMERIC(20,8) NOT NULL,
    hour_return          NUMERIC(12,6),
    volume_base          NUMERIC(24,8),

    -- Rolling z-score detector
    return_zscore        NUMERIC(10,4),
    is_anomaly_zscore    BOOLEAN      NOT NULL DEFAULT FALSE,
    zscore_threshold     REAL         NOT NULL DEFAULT 3.0,

    -- Isolation Forest detector
    iforest_score        NUMERIC(10,6),   -- más negativo = más anómalo
    is_anomaly_iforest   BOOLEAN      NOT NULL DEFAULT FALSE,

    -- Consenso: TRUE si ambos detectores lo marcan
    is_anomaly_consensus BOOLEAN      NOT NULL DEFAULT FALSE,

    model_version        TEXT         NOT NULL DEFAULT 'iforest-v1+zscore-w24',
    detected_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),

    PRIMARY KEY (symbol, event_hour)
);

CREATE INDEX IF NOT EXISTS idx_price_anom_hour ON ml.price_anomalies (event_hour DESC);
CREATE INDEX IF NOT EXISTS idx_price_anom_flag ON ml.price_anomalies (is_anomaly_consensus)
    WHERE is_anomaly_consensus = TRUE;

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA ml TO cryptopulse;
