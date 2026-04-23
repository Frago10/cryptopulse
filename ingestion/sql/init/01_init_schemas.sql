-- =============================================================================
-- CryptoPulse — Inicialización de Postgres
-- Este script se ejecuta UNA sola vez cuando el contenedor de Postgres arranca
-- por primera vez. Crea la base de datos de Airflow y los esquemas del warehouse.
-- =============================================================================

-- Base de datos para metadata de Airflow
CREATE DATABASE airflow;

-- Esquemas del warehouse (dentro de la base `cryptopulse`)
\c cryptopulse;

CREATE SCHEMA IF NOT EXISTS raw;       -- datos crudos (desde MinIO o streaming)
CREATE SCHEMA IF NOT EXISTS staging;   -- capa silver (dbt)
CREATE SCHEMA IF NOT EXISTS marts;     -- capa gold (dbt)
CREATE SCHEMA IF NOT EXISTS ml;        -- outputs de modelos ML

-- Tabla de ticks en tiempo real (la llenará el consumer de Fase 2)
CREATE TABLE IF NOT EXISTS raw.ticks (
    id               BIGSERIAL PRIMARY KEY,
    symbol           TEXT        NOT NULL,
    event_time       TIMESTAMPTZ NOT NULL,
    price            NUMERIC(20, 8) NOT NULL,
    price_change_pct NUMERIC(10, 4),
    volume_base      NUMERIC(24, 8),
    volume_quote     NUMERIC(24, 8),
    trades_count     BIGINT,
    bid              NUMERIC(20, 8),
    ask              NUMERIC(20, 8),
    ingested_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ticks_symbol_time ON raw.ticks (symbol, event_time DESC);
CREATE INDEX IF NOT EXISTS idx_ticks_event_time ON raw.ticks (event_time DESC);

-- Permisos
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA raw TO cryptopulse;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA staging TO cryptopulse;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA marts TO cryptopulse;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA ml TO cryptopulse;
