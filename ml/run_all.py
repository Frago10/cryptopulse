"""
Orquestador de la Fase 5: corre VADER + anomaly detection en un solo comando.

Uso:
    python -m ml.run_all
    python -m ml.run_all --skip-sentiment
    python -m ml.run_all --skip-anomalies

En Airflow (Fase 6) cada módulo se invocará como su propia task, pero tener
este entrypoint único facilita la ejecución manual y CI/CD.
"""
from __future__ import annotations

import argparse
import sys

from ingestion.utils.logging_config import configure_logging, get_logger
from ml.anomaly.price_anomalies import run as run_anomalies
from ml.sentiment.vader_scorer import run as run_sentiment

log = get_logger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fase 5 — corre los jobs de ML")
    parser.add_argument("--skip-sentiment", action="store_true")
    parser.add_argument("--skip-anomalies", action="store_true")
    parser.add_argument("--lookback-days", type=int, default=30,
                        help="Para sentiment (default: 30)")
    parser.add_argument("--lookback-hours", type=int, default=24 * 30,
                        help="Para anomalies (default: 720 = 30 días)")
    args = parser.parse_args(argv)

    configure_logging()

    if not args.skip_sentiment:
        log.info("ml.run_all.sentiment.start")
        run_sentiment(lookback_days=args.lookback_days)
        log.info("ml.run_all.sentiment.done")

    if not args.skip_anomalies:
        log.info("ml.run_all.anomalies.start")
        run_anomalies(lookback_hours=args.lookback_hours)
        log.info("ml.run_all.anomalies.done")

    return 0


if __name__ == "__main__":
    sys.exit(main())
