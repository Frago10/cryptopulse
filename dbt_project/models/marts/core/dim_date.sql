{{
    config(
        materialized='table',
        tags=['core', 'dim']
    )
}}

/*
  dim_date
  --------
  Spine de fechas. Generamos un rango lo suficientemente ancho (5 años)
  para cubrir backfills históricos + presente + algún look-ahead.

  date_key = YYYYMMDD (INTEGER) — práctico para BI (ordenable, compacto).
*/

WITH spine AS (
    SELECT
        generate_series(
            DATE '2023-01-01',
            DATE '2028-12-31',
            INTERVAL '1 day'
        )::DATE AS calendar_date
)

SELECT
    (TO_CHAR(calendar_date, 'YYYYMMDD'))::INT           AS date_key,
    calendar_date                                        AS date_day,
    EXTRACT(YEAR    FROM calendar_date)::INT             AS year,
    EXTRACT(QUARTER FROM calendar_date)::INT             AS quarter,
    EXTRACT(MONTH   FROM calendar_date)::INT             AS month,
    TO_CHAR(calendar_date, 'Month')                      AS month_name,
    EXTRACT(DAY     FROM calendar_date)::INT             AS day_of_month,
    EXTRACT(DOW     FROM calendar_date)::INT             AS day_of_week,   -- 0=dom
    TO_CHAR(calendar_date, 'Day')                        AS day_name,
    EXTRACT(WEEK    FROM calendar_date)::INT             AS iso_week,
    (EXTRACT(DOW FROM calendar_date) IN (0, 6))          AS is_weekend,
    -- Flags útiles para filtros en BI
    (calendar_date = CURRENT_DATE)                       AS is_today,
    (calendar_date = CURRENT_DATE - INTERVAL '1 day')    AS is_yesterday,
    (calendar_date >= CURRENT_DATE - INTERVAL '7 days')  AS is_last_7_days,
    (calendar_date >= CURRENT_DATE - INTERVAL '30 days') AS is_last_30_days
FROM spine
