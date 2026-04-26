-- =============================================================================
-- Raw tables para los loaders batch (hydrated desde MinIO).
-- Ejecutable via psycopg2 (sin comandos meta de psql como \c).
-- =============================================================================

-- ---- CoinGecko market_data (snapshot por hora) ----
CREATE TABLE IF NOT EXISTS raw.coingecko_markets (
    id                              TEXT        NOT NULL,
    symbol                          TEXT        NOT NULL,
    name                            TEXT        NOT NULL,
    image                           TEXT,
    current_price                   NUMERIC(24,8),
    market_cap                      NUMERIC(30,2),
    market_cap_rank                 INTEGER,
    fully_diluted_valuation         NUMERIC(30,2),
    total_volume                    NUMERIC(30,2),
    high_24h                        NUMERIC(24,8),
    low_24h                         NUMERIC(24,8),
    price_change_24h                NUMERIC(24,8),
    price_change_percentage_24h     NUMERIC(12,4),
    price_change_percentage_1h_in_currency  NUMERIC(12,4),
    price_change_percentage_24h_in_currency NUMERIC(12,4),
    price_change_percentage_7d_in_currency  NUMERIC(12,4),
    market_cap_change_24h           NUMERIC(30,2),
    market_cap_change_percentage_24h NUMERIC(12,4),
    circulating_supply              NUMERIC(30,4),
    total_supply                    NUMERIC(30,4),
    max_supply                      NUMERIC(30,4),
    ath                             NUMERIC(24,8),
    ath_change_percentage           NUMERIC(12,4),
    ath_date                        TIMESTAMPTZ,
    atl                             NUMERIC(24,8),
    atl_change_percentage           NUMERIC(12,4),
    atl_date                        TIMESTAMPTZ,
    last_updated                    TIMESTAMPTZ,
    ingested_at                     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cg_markets_ingested ON raw.coingecko_markets (ingested_at DESC);
CREATE INDEX IF NOT EXISTS idx_cg_markets_symbol   ON raw.coingecko_markets (symbol);

-- ---- Fear & Greed Index ----
CREATE TABLE IF NOT EXISTS raw.fear_greed_index (
    index_date          TIMESTAMPTZ NOT NULL,
    value               INTEGER     NOT NULL,
    category            TEXT,
    time_until_update   TEXT,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fng_date ON raw.fear_greed_index (index_date DESC);

-- ---- Reddit posts ----
CREATE TABLE IF NOT EXISTS raw.reddit_posts (
    id              TEXT        PRIMARY KEY,
    subreddit       TEXT        NOT NULL,
    title           TEXT        NOT NULL,
    selftext        TEXT,
    author          TEXT,
    score           INTEGER,
    upvote_ratio    REAL,
    num_comments    INTEGER,
    created_utc     TIMESTAMPTZ NOT NULL,
    url             TEXT,
    is_self         BOOLEAN,
    over_18         BOOLEAN,
    permalink       TEXT,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_reddit_subreddit ON raw.reddit_posts (subreddit);
CREATE INDEX IF NOT EXISTS idx_reddit_created   ON raw.reddit_posts (created_utc DESC);

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA raw TO cryptopulse;
