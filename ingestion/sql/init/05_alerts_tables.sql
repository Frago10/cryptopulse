-- =============================================================================
-- 05_alerts_tables.sql
-- Tablas de soporte para el modulo de alertas (Telegram).
--
-- alerts.telegram_sent: dedup de alertas enviadas. Granularidad:
--   una fila por (symbol, event_hour, kind). 'kind' deja espacio
--   para futuros canales (slack, email, etc.).
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS alerts;
GRANT USAGE ON SCHEMA alerts TO cryptopulse;

CREATE TABLE IF NOT EXISTS alerts.telegram_sent (
    alert_key      TEXT        NOT NULL,
    symbol         TEXT        NOT NULL,
    event_hour     TIMESTAMPTZ NOT NULL,
    severity       NUMERIC(10,4),
    sent_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    response_ok    BOOLEAN     NOT NULL DEFAULT TRUE,
    PRIMARY KEY (alert_key)
);

CREATE INDEX IF NOT EXISTS ix_telegram_sent_event_hour
    ON alerts.telegram_sent (event_hour DESC);

GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA alerts TO cryptopulse;
ALTER DEFAULT PRIVILEGES IN SCHEMA alerts
    GRANT SELECT, INSERT, UPDATE ON TABLES TO cryptopulse;
