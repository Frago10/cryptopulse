"""
Wrapper de MinIO (S3-compatible) para la capa BRONZE.

Responsabilidad única: dado un DataFrame de pandas y un dataset/dominio,
escribirlo como Parquet particionado por fecha/hora en el bucket correcto.

Layout de particiones (Hive-style, compatible con Spark, dbt-external-tables,
AWS Glue, Athena, etc.):

    s3://bronze/<source>/<dataset>/dt=YYYY-MM-DD/hh=HH/<timestamp>.parquet

Ejemplo:

    s3://bronze/coingecko/market_data/dt=2026-04-22/hh=19/1713812345.parquet
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Optional

import boto3
import pandas as pd
from botocore.client import Config

from ingestion.utils.config import settings
from ingestion.utils.logging_config import get_logger

log = get_logger(__name__)


class MinIOClient:
    """Cliente S3 apuntando a MinIO local."""

    def __init__(self) -> None:
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.MINIO_ENDPOINT,
            aws_access_key_id=settings.MINIO_ROOT_USER,
            aws_secret_access_key=settings.MINIO_ROOT_PASSWORD,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",  # MinIO ignora la región pero boto3 la exige
        )

    # ---- Operaciones de bucket ----
    def ensure_bucket(self, bucket: str) -> None:
        try:
            self.client.head_bucket(Bucket=bucket)
        except Exception:
            log.info("bucket.create", bucket=bucket)
            self.client.create_bucket(Bucket=bucket)

    # ---- Escritura principal ----
    def write_parquet(
        self,
        df: pd.DataFrame,
        *,
        source: str,
        dataset: str,
        bucket: Optional[str] = None,
        partition_ts: Optional[datetime] = None,
        overwrite_partition: bool = True,
    ) -> str:
        """
        Escribe un DataFrame como Parquet particionado por fecha/hora.

        Args:
            df: DataFrame a persistir.
            source: nombre del origen (coingecko, reddit, fng, binance).
            dataset: nombre del dataset (market_data, posts, index...).
            bucket: bucket destino; por default el bronze configurado.
            partition_ts: timestamp para calcular la partición; default = ahora UTC.
            overwrite_partition: si True borra la partición antes de escribir
                                 (útil para reejecutar un run sin duplicar).

        Returns:
            Clave (key) S3 completa del objeto creado.
        """
        if df.empty:
            log.warning("write_parquet.empty_dataframe", source=source, dataset=dataset)
            return ""

        bucket = bucket or settings.MINIO_BUCKET_BRONZE
        ts = partition_ts or datetime.now(timezone.utc)
        dt_part = ts.strftime("%Y-%m-%d")
        hh_part = ts.strftime("%H")
        epoch_ms = int(ts.timestamp() * 1000)

        prefix = f"{source}/{dataset}/dt={dt_part}/hh={hh_part}/"
        key = f"{prefix}{epoch_ms}.parquet"

        self.ensure_bucket(bucket)

        if overwrite_partition:
            self._delete_prefix(bucket, prefix)

        # Serializar a Parquet en memoria
        buffer = io.BytesIO()
        df.to_parquet(buffer, engine="pyarrow", compression="snappy", index=False)
        buffer.seek(0)

        self.client.put_object(
            Bucket=bucket,
            Key=key,
            Body=buffer.getvalue(),
            ContentType="application/octet-stream",
        )

        log.info(
            "write_parquet.ok",
            bucket=bucket,
            key=key,
            rows=len(df),
            size_kb=round(buffer.getbuffer().nbytes / 1024, 1),
        )
        return key

    def _delete_prefix(self, bucket: str, prefix: str) -> int:
        """Borra todos los objetos bajo un prefijo (para idempotencia)."""
        paginator = self.client.get_paginator("list_objects_v2")
        to_delete: list[dict[str, str]] = []
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []) or []:
                to_delete.append({"Key": obj["Key"]})
        if not to_delete:
            return 0
        self.client.delete_objects(Bucket=bucket, Delete={"Objects": to_delete})
        log.info("delete_prefix.ok", bucket=bucket, prefix=prefix, deleted=len(to_delete))
        return len(to_delete)


# Singleton para reutilizar la conexión
_client: Optional[MinIOClient] = None


def get_minio() -> MinIOClient:
    global _client
    if _client is None:
        _client = MinIOClient()
    return _client
