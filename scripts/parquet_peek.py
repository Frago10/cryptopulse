"""
Visor rápido de Parquets en MinIO.

Uso:
    python scripts/parquet_peek.py              # Lista todo el bucket bronze
    python scripts/parquet_peek.py coingecko    # Filtra por prefijo
    python scripts/parquet_peek.py --latest     # Abre el Parquet más reciente por dataset
    python scripts/parquet_peek.py --key coingecko/market_data/dt=.../hh=.../xxx.parquet

Este script es también la forma fácil de validar qué quedó en bronze
cuando MinIO no te da preview del archivo.
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

# Permitir importar ingestion.* aunque se ejecute desde scripts/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from ingestion.utils.config import settings  # noqa: E402
from ingestion.utils.minio_client import get_minio  # noqa: E402


def list_objects(prefix: str = "") -> list[dict]:
    minio = get_minio()
    paginator = minio.client.get_paginator("list_objects_v2")
    rows = []
    for page in paginator.paginate(Bucket=settings.MINIO_BUCKET_BRONZE, Prefix=prefix):
        for obj in page.get("Contents", []) or []:
            rows.append({
                "key": obj["Key"],
                "size_kb": round(obj["Size"] / 1024, 1),
                "last_modified": obj["LastModified"],
            })
    return rows


def read_parquet(key: str) -> pd.DataFrame:
    minio = get_minio()
    resp = minio.client.get_object(Bucket=settings.MINIO_BUCKET_BRONZE, Key=key)
    return pd.read_parquet(io.BytesIO(resp["Body"].read()))


def cmd_list(prefix: str) -> None:
    objs = list_objects(prefix)
    if not objs:
        print(f"(sin objetos bajo bronze/{prefix})")
        return
    print(f"{'SIZE KB':>8}  {'LAST MODIFIED':20}  KEY")
    for o in objs:
        print(f"{o['size_kb']:>8}  {str(o['last_modified'])[:19]}  {o['key']}")


def cmd_latest(prefix: str) -> None:
    objs = list_objects(prefix)
    if not objs:
        print(f"(sin objetos bajo bronze/{prefix})")
        return
    latest = max(objs, key=lambda x: x["last_modified"])
    print(f"Leyendo: {latest['key']}  ({latest['size_kb']} KB)\n")
    df = read_parquet(latest["key"])
    print(f"Shape: {df.shape}")
    print(f"Columnas ({len(df.columns)}): {list(df.columns)}\n")
    print("--- head(10) ---")
    with pd.option_context("display.max_columns", 20, "display.width", 200):
        print(df.head(10).to_string())
    print("\n--- dtypes ---")
    print(df.dtypes)


def cmd_key(key: str) -> None:
    df = read_parquet(key)
    print(f"Shape: {df.shape}")
    print(df.head(20).to_string())


def main() -> None:
    ap = argparse.ArgumentParser(description="Visor de parquets en MinIO bronze")
    ap.add_argument("prefix", nargs="?", default="", help="Filtra por prefijo (ej: coingecko)")
    ap.add_argument("--latest", action="store_true", help="Muestra el parquet mas reciente")
    ap.add_argument("--key", type=str, help="Clave exacta de un parquet a leer")
    args = ap.parse_args()

    if args.key:
        cmd_key(args.key)
    elif args.latest:
        cmd_latest(args.prefix)
    else:
        cmd_list(args.prefix)


if __name__ == "__main__":
    main()
