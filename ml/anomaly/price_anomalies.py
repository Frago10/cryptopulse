"""
Detección de anomalías en precios horarios (OHLCV).

Ensamble de dos detectores complementarios:

  1. Rolling z-score sobre `hour_return`
     ---------------------------------------
     Ventana móvil de 24 horas. Marca |z| >= threshold (default 3.0).
     Rápido, interpretable, detecta spikes bruscos.

  2. Isolation Forest (unsupervised)
     -------------------------------
     Features: [hour_return, volume_base, avg_spread]
     Entrenado por-símbolo (cada crypto tiene dinámica propia).
     Detecta patrones raros MULTIVARIADOS — p.ej. subida chica de precio
     con volumen 100x anómalo (pump inusual) que el z-score de returns se
     comería.

La tabla final reporta ambas señales y una columna `is_anomaly_consensus`
(ambos detectores de acuerdo) — ideal para alertas de alta precisión.

Uso:
    python -m ml.anomaly.price_anomalies
    python -m ml.anomaly.price_anomalies --lookback-hours 168
    python -m ml.anomaly.price_anomalies --contamination 0.02
"""
from __future__ import annotations

import argparse
import sys
from typing import Optional

import numpy as np
import pandas as pd

from ingestion.utils.logging_config import configure_logging, get_logger
from ml.utils.ml_io import fetch_hourly_prices, upsert_price_anomalies

log = get_logger(__name__)

MODEL_VERSION = "iforest-v1+zscore-w24"
DEFAULT_ZSCORE_WINDOW = 24
DEFAULT_ZSCORE_THRESHOLD = 3.0
DEFAULT_CONTAMINATION = 0.05   # ~5% de puntos esperados anómalos
DEFAULT_MIN_POINTS = 48        # mínimo para entrenar IF con cierta confianza


# -----------------------------------------------------------------------------
# Detectores
# -----------------------------------------------------------------------------
def rolling_zscore(series: pd.Series, window: int = DEFAULT_ZSCORE_WINDOW) -> pd.Series:
    """
    Rolling z-score con ventana `window`. Las primeras `window-1` filas
    salen NaN (no hay historia suficiente) — las dejamos así a propósito.
    """
    mean = series.rolling(window=window, min_periods=window).mean()
    std = series.rolling(window=window, min_periods=window).std()
    z = (series - mean) / std.replace(0, np.nan)
    return z


def iforest_scores(features: pd.DataFrame, contamination: float) -> tuple[np.ndarray, np.ndarray]:
    """
    Ajusta IsolationForest en `features` (NaNs ya rellenados) y devuelve:
      - decision_function (float, más negativo = más anómalo)
      - predict (1=normal, -1=anómalo)
    """
    try:
        from sklearn.ensemble import IsolationForest
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "Falta scikit-learn. Instalalo con: pip install scikit-learn"
        ) from e

    model = IsolationForest(
        n_estimators=100,
        contamination=contamination,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(features)
    scores = model.decision_function(features)
    preds = model.predict(features)   # 1 / -1
    return scores, preds


# -----------------------------------------------------------------------------
# Pipeline por-símbolo
# -----------------------------------------------------------------------------
def detect_for_symbol(
    df: pd.DataFrame,
    *,
    window: int = DEFAULT_ZSCORE_WINDOW,
    zscore_threshold: float = DEFAULT_ZSCORE_THRESHOLD,
    contamination: float = DEFAULT_CONTAMINATION,
    min_points: int = DEFAULT_MIN_POINTS,
) -> pd.DataFrame:
    """
    Corre ambos detectores sobre una serie por símbolo.
    Espera `df` ordenado por event_hour ASC.
    """
    df = df.sort_values("event_hour").reset_index(drop=True)
    out = df[["symbol", "event_hour", "close", "hour_return", "volume_base"]].copy()

    # -------- Detector 1: rolling z-score sobre returns -----------------------
    zs = rolling_zscore(df["hour_return"].astype(float), window=window)
    out["return_zscore"] = zs.round(4)
    out["is_anomaly_zscore"] = (zs.abs() >= zscore_threshold).fillna(False)
    out["zscore_threshold"] = float(zscore_threshold)

    # -------- Detector 2: IsolationForest multivariado ------------------------
    feats = df[["hour_return", "volume_base", "avg_spread"]].astype(float).copy()
    # Imputar NaN con mediana — IF no tolera NaN
    feats = feats.fillna(feats.median(numeric_only=True)).fillna(0.0)

    if len(feats) >= min_points:
        scores, preds = iforest_scores(feats, contamination=contamination)
        out["iforest_score"] = np.round(scores, 6)
        out["is_anomaly_iforest"] = (preds == -1)
    else:
        # Poca data — no entrenamos, marcamos NaN/False
        out["iforest_score"] = np.nan
        out["is_anomaly_iforest"] = False
        log.warning("anomaly.iforest.skipped",
                    symbol=df["symbol"].iloc[0] if not df.empty else None,
                    rows=len(feats), min_points=min_points)

    # -------- Consenso --------------------------------------------------------
    out["is_anomaly_consensus"] = out["is_anomaly_zscore"] & out["is_anomaly_iforest"]
    out["model_version"] = MODEL_VERSION
    return out


# -----------------------------------------------------------------------------
# Entrypoint
# -----------------------------------------------------------------------------
def run(
    lookback_hours: int = 24 * 30,
    window: int = DEFAULT_ZSCORE_WINDOW,
    zscore_threshold: float = DEFAULT_ZSCORE_THRESHOLD,
    contamination: float = DEFAULT_CONTAMINATION,
) -> int:
    configure_logging()

    df = fetch_hourly_prices(lookback_hours=lookback_hours)
    if df.empty:
        log.warning("anomaly.no_data", lookback_hours=lookback_hours)
        return 0

    all_out: list[pd.DataFrame] = []
    for symbol, sub in df.groupby("symbol", sort=False):
        log.info("anomaly.detect", symbol=symbol, rows=len(sub))
        res = detect_for_symbol(
            sub,
            window=window,
            zscore_threshold=zscore_threshold,
            contamination=contamination,
        )
        all_out.append(res)

    if not all_out:
        return 0

    final = pd.concat(all_out, ignore_index=True)

    # Resumen: cuántos puntos y cuántos anómalos
    n_z = int(final["is_anomaly_zscore"].sum())
    n_if = int(final["is_anomaly_iforest"].sum())
    n_cons = int(final["is_anomaly_consensus"].sum())
    log.info("anomaly.summary",
             total=len(final),
             anom_zscore=n_z,
             anom_iforest=n_if,
             anom_consensus=n_cons,
             symbols=final["symbol"].nunique())

    written = upsert_price_anomalies(final)
    log.info("anomaly.written", rows=written)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hybrid price-anomaly detector")
    parser.add_argument("--lookback-hours", type=int, default=24 * 30,
                        help="Ventana de datos a scorear (default: 720 = 30 días)")
    parser.add_argument("--window", type=int, default=DEFAULT_ZSCORE_WINDOW,
                        help="Ventana del rolling z-score en horas (default: 24)")
    parser.add_argument("--zscore-threshold", type=float, default=DEFAULT_ZSCORE_THRESHOLD,
                        help="|z| >= threshold => anomalía (default: 3.0)")
    parser.add_argument("--contamination", type=float, default=DEFAULT_CONTAMINATION,
                        help="Proporción esperada de anomalías para IsolationForest (default: 0.05)")
    args = parser.parse_args(argv)

    run(
        lookback_hours=args.lookback_hours,
        window=args.window,
        zscore_threshold=args.zscore_threshold,
        contamination=args.contamination,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
