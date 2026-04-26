"""
quality.suites
==============
Definicion programatica de los ExpectationSuites de Great Expectations.

Por que en codigo y no en YAML?
  * Reproducibilidad: el diff de un cambio se ve limpio en git.
  * Refactor facil: renombrar un campo se hace con find-and-replace.
  * Tests del pipeline: podemos generar suites en pytest y comparar.

Cada funcion `build_*_suite` retorna una lista de tuplas
(expectation_type, kwargs) que `run_checkpoint` convierte en Expectations.
No usamos el PandasDataset API - usamos el SqlAlchemyDataset que soporta
expectativas push-down directamente sobre Postgres.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

# --------------------------------------------------------------------------- #
# Whitelists de simbolos.
#
# El pipeline usa DOS convenciones distintas por diseno:
#   * raw.ticks (streaming Binance) -> BTCUSDT, ETHUSDT, ... (pair completo)
#   * gold layer  (dbt sobre CoinGecko) -> BTC, ETH, ... (base currency)
#
# Mantener ambos conjuntos explicitos en lugar de normalizar es deliberado:
# asi cada capa puede evolucionar sin romper las otras.
# --------------------------------------------------------------------------- #
TRACKED_SYMBOLS_BINANCE = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT",
    "XRPUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT",
]
TRACKED_SYMBOLS_BASE = [
    "BTC", "ETH", "SOL", "ADA",
    "XRP", "DOGE", "AVAX", "DOT",
]
# Alias retro-compatible (por si algun script externo lo importa)
TRACKED_SYMBOLS = TRACKED_SYMBOLS_BINANCE

SENTIMENT_LABELS = ["positive", "neutral", "negative"]

# Expectation = (tipo, kwargs)
Expectation = Tuple[str, Dict[str, Any]]


# --------------------------------------------------------------------------- #
# raw.ticks - el core del pipeline streaming
# --------------------------------------------------------------------------- #
def build_raw_ticks_suite() -> List[Expectation]:
    return [
        ("expect_table_columns_to_match_set", {
            "column_set": [
                "id", "symbol", "event_time", "price", "price_change_pct",
                "volume_base", "volume_quote", "trades_count", "bid", "ask",
                "ingested_at",
            ],
            "exact_match": False,
        }),
        ("expect_column_values_to_not_be_null", {"column": "symbol"}),
        ("expect_column_values_to_not_be_null", {"column": "event_time"}),
        ("expect_column_values_to_not_be_null", {"column": "price"}),
        ("expect_column_values_to_be_between", {
            "column": "price", "min_value": 0, "strict_min": True,
        }),
        ("expect_column_values_to_be_between", {
            "column": "volume_base", "min_value": 0,
        }),
        # Dominio de simbolos (convencion Binance: BTCUSDT, ETHUSDT, ...)
        ("expect_column_values_to_be_in_set", {
            "column": "symbol", "value_set": TRACKED_SYMBOLS_BINANCE,
        }),
    ]


# --------------------------------------------------------------------------- #
# analytics_marts.fact_prices_hourly - el fact gold principal
# --------------------------------------------------------------------------- #
def build_fact_prices_hourly_suite() -> List[Expectation]:
    return [
        ("expect_compound_columns_to_be_unique", {
            "column_list": ["symbol", "event_hour"],
        }),
        ("expect_column_values_to_not_be_null", {"column": "open"}),
        ("expect_column_values_to_not_be_null", {"column": "close"}),
        ("expect_column_values_to_be_between", {
            "column": "open", "min_value": 0, "strict_min": True,
        }),
        ("expect_column_values_to_be_between", {
            "column": "close", "min_value": 0, "strict_min": True,
        }),
        # high >= low (regla de mercado)
        # Nota: en GE 0.18.x el expectation type es lowercase a/b, pero los
        # kwargs siguen siendo column_A / column_B (mixto, raro pero asi es).
        ("expect_column_pair_values_a_to_be_greater_than_b", {
            "column_A": "high", "column_B": "low", "or_equal": True,
        }),
        ("expect_column_values_to_be_between", {
            "column": "ticks_count", "min_value": 1,
        }),
        # Dominio de simbolos (convencion gold: BTC, ETH, ... sin USDT)
        ("expect_column_values_to_be_in_set", {
            "column": "symbol", "value_set": TRACKED_SYMBOLS_BASE,
        }),
    ]


# --------------------------------------------------------------------------- #
# analytics_marts.mart_anomaly_alerts - el mart que alimenta Telegram
# --------------------------------------------------------------------------- #
def build_mart_anomaly_alerts_suite() -> List[Expectation]:
    return [
        ("expect_column_values_to_be_between", {
            "column": "severity_score", "min_value": 0,
        }),
        ("expect_column_values_to_not_be_null", {"column": "is_anomaly_zscore"}),
        ("expect_column_values_to_not_be_null", {"column": "is_anomaly_iforest"}),
        ("expect_column_values_to_not_be_null", {"column": "is_anomaly_consensus"}),
        ("expect_column_values_to_not_be_null", {"column": "anomaly_model_version"}),
        ("expect_column_values_to_not_be_null", {"column": "detected_at"}),
        # Dominio de simbolos (convencion gold: BTC, ETH, ... sin USDT)
        ("expect_column_values_to_be_in_set", {
            "column": "symbol", "value_set": TRACKED_SYMBOLS_BASE,
        }),
    ]


# --------------------------------------------------------------------------- #
# ml.reddit_sentiment - outputs de VADER
# --------------------------------------------------------------------------- #
def build_reddit_sentiment_suite() -> List[Expectation]:
    return [
        ("expect_column_values_to_be_between", {
            "column": "compound", "min_value": -1.0, "max_value": 1.0,
        }),
        ("expect_column_values_to_be_between", {
            "column": "pos", "min_value": 0.0, "max_value": 1.0,
        }),
        ("expect_column_values_to_be_between", {
            "column": "neu", "min_value": 0.0, "max_value": 1.0,
        }),
        ("expect_column_values_to_be_between", {
            "column": "neg", "min_value": 0.0, "max_value": 1.0,
        }),
        ("expect_column_values_to_be_in_set", {
            "column": "sentiment_label", "value_set": SENTIMENT_LABELS,
        }),
        ("expect_column_values_to_not_be_null", {"column": "post_id"}),
        ("expect_column_values_to_not_be_null", {"column": "model_version"}),
    ]


# --------------------------------------------------------------------------- #
# Registro de suites: nombre logico -> (schema, tabla, builder, critico)
# "critico" = si falla esta suite, el DAG debe fallar.
# --------------------------------------------------------------------------- #
SUITES: Dict[str, Dict[str, Any]] = {
    "raw_ticks": {
        "schema": "raw",
        "table":  "ticks",
        "builder": build_raw_ticks_suite,
        "critical": True,
    },
    "fact_prices_hourly": {
        "schema": "analytics_marts",
        "table":  "fact_prices_hourly",
        "builder": build_fact_prices_hourly_suite,
        "critical": True,
    },
    "mart_anomaly_alerts": {
        "schema": "analytics_marts",
        "table":  "mart_anomaly_alerts",
        "builder": build_mart_anomaly_alerts_suite,
        "critical": False,
    },
    "reddit_sentiment": {
        "schema": "ml",
        "table":  "reddit_sentiment",
        "builder": build_reddit_sentiment_suite,
        "critical": False,
    },
}
