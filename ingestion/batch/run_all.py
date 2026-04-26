"""
Runner maestro para los 3 loaders batch.

Uso:  python -m ingestion.batch.run_all

Lo llamará Airflow en la Fase 6 dentro de un DAG. Por ahora sirve para
lanzar manualmente una ingesta completa y ver Parquets en MinIO.
"""
from __future__ import annotations

from ingestion.batch import coingecko_loader, fng_loader, reddit_loader
from ingestion.utils.logging_config import configure_logging, get_logger

log = get_logger(__name__)


def main() -> None:
    configure_logging()
    results: dict[str, str] = {}

    # --- CoinGecko (siempre, no requiere auth) ---
    try:
        results["coingecko"] = coingecko_loader.run()
    except Exception as exc:
        log.error("run_all.coingecko.failed", error=str(exc))
        results["coingecko"] = f"FAILED: {exc}"

    # --- Fear & Greed (siempre, no requiere auth) ---
    try:
        results["fng"] = fng_loader.run()
    except Exception as exc:
        log.error("run_all.fng.failed", error=str(exc))
        results["fng"] = f"FAILED: {exc}"

    # --- Reddit (skip suave si no hay credenciales) ---
    try:
        results["reddit"] = reddit_loader.run()
    except RuntimeError as exc:
        log.warning("run_all.reddit.skipped", reason=str(exc))
        results["reddit"] = f"SKIPPED: {exc}"
    except Exception as exc:
        log.error("run_all.reddit.failed", error=str(exc))
        results["reddit"] = f"FAILED: {exc}"

    print("\n=== Resumen de ingesta ===")
    for source, key in results.items():
        print(f"  {source:12} -> {key}")


if __name__ == "__main__":
    main()
