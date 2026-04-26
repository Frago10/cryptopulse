{{
    config(
        materialized='view',
        tags=['staging', 'ml']
    )
}}

/*
  stg_price_anomalies
  -------------------
  Staging view sobre `ml.price_anomalies`. Expone date_key y un flag
  "any detector" (útil para analítica menos estricta que el consensus).
*/

SELECT
    symbol,
    event_hour,
    DATE_TRUNC('day', event_hour)::DATE                 AS event_date,
    (TO_CHAR(event_hour, 'YYYYMMDD'))::INT              AS date_key,
    close,
    hour_return,
    volume_base,

    return_zscore,
    is_anomaly_zscore,
    zscore_threshold,

    iforest_score,
    is_anomaly_iforest,

    is_anomaly_consensus,
    (is_anomaly_zscore OR is_anomaly_iforest)           AS is_anomaly_any,

    model_version,
    detected_at
FROM {{ source('ml', 'price_anomalies') }}
