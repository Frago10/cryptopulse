"""
Tests para el loader de CoinGecko.

Mockeamos la API externa para no depender de red/rate-limits y
validamos que el `transform` produce las columnas esperadas.
"""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from ingestion.batch import coingecko_loader


SAMPLE_RAW = [
    {
        "id": "bitcoin",
        "symbol": "btc",
        "name": "Bitcoin",
        "current_price": 65000.0,
        "market_cap": 1_280_000_000_000,
        "total_volume": 35_000_000_000,
        "price_change_percentage_24h": 2.5,
        "last_updated": "2026-04-22T19:00:00.000Z",
        "ath_date": "2024-03-14T00:00:00.000Z",
        "atl_date": "2013-07-06T00:00:00.000Z",
    },
    {
        "id": "ethereum",
        "symbol": "eth",
        "name": "Ethereum",
        "current_price": 3200.0,
        "market_cap": 385_000_000_000,
        "total_volume": 15_000_000_000,
        "price_change_percentage_24h": -1.2,
        "last_updated": "2026-04-22T19:00:00.000Z",
        "ath_date": "2021-11-10T00:00:00.000Z",
        "atl_date": "2015-10-20T00:00:00.000Z",
    },
]


def test_transform_adds_metadata_columns():
    df = coingecko_loader.transform(SAMPLE_RAW)
    assert len(df) == 2
    for col in ("_ingested_at", "_source", "_dataset"):
        assert col in df.columns
    assert (df["_source"] == "coingecko").all()
    assert (df["_dataset"] == "market_data").all()


def test_transform_parses_datetime_columns():
    df = coingecko_loader.transform(SAMPLE_RAW)
    assert pd.api.types.is_datetime64_any_dtype(df["last_updated"])
    assert pd.api.types.is_datetime64_any_dtype(df["ath_date"])


def test_transform_empty_input_returns_empty_df():
    df = coingecko_loader.transform([])
    assert df.empty


def test_fetch_calls_correct_endpoint():
    with patch("ingestion.batch.coingecko_loader.requests.get") as mock_get:
        mock_get.return_value.json.return_value = SAMPLE_RAW
        mock_get.return_value.raise_for_status = lambda: None
        result = coingecko_loader.fetch(per_page=2)

    assert len(result) == 2
    call_args = mock_get.call_args
    assert "coins/markets" in call_args[0][0]
    assert call_args[1]["params"]["vs_currency"] == "usd"
    assert call_args[1]["params"]["per_page"] == 2
