"""
Configuración centralizada con pydantic-settings.

Lee el .env una sola vez y expone un objeto tipado `settings` que todos
los módulos pueden importar. Esto evita tener `os.getenv("...")` regado
por todo el código y da autocompletado en el IDE.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Raíz del proyecto (tres niveles arriba: utils -> ingestion -> cryptopulse)
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ---- Postgres ----
    POSTGRES_USER: str = "cryptopulse"
    POSTGRES_PASSWORD: str = "changeme_in_prod"
    POSTGRES_DB: str = "cryptopulse"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432

    # ---- MinIO ----
    MINIO_ROOT_USER: str = "minio"
    MINIO_ROOT_PASSWORD: str = "minio12345"
    MINIO_ENDPOINT: str = "http://localhost:9000"
    MINIO_BUCKET_BRONZE: str = "bronze"
    MINIO_BUCKET_SILVER: str = "silver"
    MINIO_BUCKET_GOLD: str = "gold"

    # ---- APIs ----
    COINGECKO_API_URL: str = "https://api.coingecko.com/api/v3"
    BINANCE_WS_URL: str = "wss://stream.binance.com:9443/ws"
    FNG_API_URL: str = "https://api.alternative.me/fng/"

    # ---- Reddit ----
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""
    REDDIT_USER_AGENT: str = "cryptopulse/0.1"

    # ---- Kafka ----
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_TOPIC_TICKS: str = "ticks"

    # ---- Símbolos ----
    TRACKED_SYMBOLS: str = "BTCUSDT,ETHUSDT,SOLUSDT,ADAUSDT,XRPUSDT,DOGEUSDT,AVAXUSDT,DOTUSDT"

    # ---- Telegram ----
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # ---- LLM (Streamlit Alert Explainer) ----
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-haiku-4-5-20251001"

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def symbols_list(self) -> List[str]:
        return [s.strip().upper() for s in self.TRACKED_SYMBOLS.split(",") if s.strip()]

    @property
    def coingecko_ids(self) -> List[str]:
        """
        Mapea símbolos de Binance (BTCUSDT) a IDs de CoinGecko (bitcoin).
        Solo incluimos los más comunes; se puede extender.
        """
        mapping = {
            "BTCUSDT": "bitcoin",
            "ETHUSDT": "ethereum",
            "SOLUSDT": "solana",
            "ADAUSDT": "cardano",
            "XRPUSDT": "ripple",
            "DOGEUSDT": "dogecoin",
            "AVAXUSDT": "avalanche-2",
            "DOTUSDT": "polkadot",
            "MATICUSDT": "matic-network",
            "LINKUSDT": "chainlink",
        }
        return [mapping[s] for s in self.symbols_list if s in mapping]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton para cachear la lectura del .env."""
    return Settings()


# atajo de import
settings = get_settings()
