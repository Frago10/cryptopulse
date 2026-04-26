{{
    config(
        materialized='table',
        tags=['core', 'dim']
    )
}}

/*
  dim_coin
  --------
  Dimensión: una fila por moneda. Toma el snapshot MÁS reciente de
  CoinGecko para cada coin_id (la metadata como name, image_url, supply
  no cambia entre snapshots — usamos el último para tener la versión
  más completa).

  Clave subrogada (coin_key) = hash estable de coin_id.
*/

WITH latest AS (
    SELECT
        coin_id,
        symbol,
        coin_name,
        image_url,
        max_supply,
        circulating_supply,
        total_supply,
        ROW_NUMBER() OVER (PARTITION BY coin_id ORDER BY ingested_at DESC) AS rn
    FROM {{ ref('stg_coingecko_markets') }}
),

base AS (
    SELECT
        coin_id,
        symbol,
        coin_name,
        image_url,
        max_supply,
        circulating_supply,
        total_supply
    FROM latest
    WHERE rn = 1
)

SELECT
    {{ dbt_utils.generate_surrogate_key(['coin_id']) }} AS coin_key,
    coin_id,
    symbol,
    coin_name,
    image_url,
    max_supply,
    circulating_supply,
    total_supply,
    CURRENT_TIMESTAMP                                   AS dw_updated_at
FROM base
