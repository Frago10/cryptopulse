"""
Tests puros (sin red, sin Docker) para la lógica de streaming.
Validan: construcción del URL, normalización del payload ticker de Binance,
y conversión mensaje JSON -> tupla para INSERT.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from ingestion.streaming.binance_producer import build_stream_url, normalize_ticker
from ingestion.streaming.redpanda_consumer import msg_to_row


# -----------------------------------------------------------------
# Fixtures: payloads representativos
# -----------------------------------------------------------------
# Formato de stream combinado: envuelto en {"stream": "...", "data": {...}}
SAMPLE_COMBINED = {
    "stream": "btcusdt@ticker",
    "data": {
        "e": "24hrTicker",
        "E": 1776920191730,
        "s": "BTCUSDT",
        "p": "1250.50",
        "P": "2.5",
        "w": "51000.00",
        "c": "51250.50",
        "Q": "0.01",
        "o": "50000.00",
        "h": "51500.00",
        "l": "49800.00",
        "v": "12345.67",
        "q": "629876543.21",
        "n": 123456,
        "b": "51250.00",
        "a": "51251.00",
    },
}


def test_build_stream_url_contains_symbols_lowercase():
    url = build_stream_url()
    assert url.startswith("wss://")
    assert "stream?streams=" in url
    # Los símbolos deben ir en minúsculas
    assert "btcusdt@ticker" in url
    assert "ethusdt@ticker" in url


def test_build_stream_url_joins_with_slash():
    url = build_stream_url()
    params = url.split("streams=")[1]
    # Al menos dos streams deben ir unidos por /
    assert "/" in params


def test_normalize_ticker_extracts_all_fields():
    tick = normalize_ticker(SAMPLE_COMBINED)
    assert tick["symbol"] == "BTCUSDT"
    assert tick["event_time"] == 1776920191730
    assert tick["price"] == 51250.5
    assert tick["price_change_pct"] == 2.5
    assert tick["volume_base"] == 12345.67
    assert tick["trades_count"] == 123456
    assert tick["bid"] == 51250.0
    assert tick["ask"] == 51251.0


def test_normalize_ticker_works_with_unwrapped_payload():
    """También debe aceptar el payload sin el wrapper `data`."""
    unwrapped = SAMPLE_COMBINED["data"]
    tick = normalize_ticker(unwrapped)
    assert tick["symbol"] == "BTCUSDT"
    assert tick["price"] == 51250.5


def test_msg_to_row_returns_tuple():
    tick = normalize_ticker(SAMPLE_COMBINED)
    row = msg_to_row(json.dumps(tick).encode("utf-8"))
    assert row is not None
    assert len(row) == 10  # 9 datos + ingested_at
    assert row[0] == "BTCUSDT"
    assert isinstance(row[1], datetime)
    assert row[1].tzinfo == timezone.utc
    assert row[2] == 51250.5
    assert isinstance(row[-1], datetime)  # ingested_at


def test_msg_to_row_returns_none_on_invalid_json():
    row = msg_to_row(b"no soy json valido")
    assert row is None


def test_msg_to_row_returns_none_on_missing_field():
    bad = json.dumps({"symbol": "BTCUSDT"}).encode()  # faltan campos
    row = msg_to_row(bad)
    assert row is None
