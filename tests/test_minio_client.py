"""
Test de integración del MinIOClient contra el MinIO local.

Requiere que `docker compose up -d` esté corriendo.
Se puede saltar con `pytest -m "not integration"`.
"""
from __future__ import annotations

import pandas as pd
import pytest

from ingestion.utils.minio_client import get_minio


@pytest.mark.integration
def test_write_parquet_roundtrip():
    df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    minio = get_minio()

    key = minio.write_parquet(
        df, source="test", dataset="roundtrip", overwrite_partition=True
    )
    assert key.startswith("test/roundtrip/dt=")
    assert key.endswith(".parquet")

    # Descargar y validar contenido
    resp = minio.client.get_object(Bucket="bronze", Key=key)
    body = resp["Body"].read()
    assert len(body) > 0
