"""Configuración del pipeline. Todo sale del entorno; nada de credenciales en código."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    root: str  # raíz del lakehouse: ruta local o s3://bucket/prefix
    dataset_bucket: str
    dataset_prefix: str
    region: str  # región del lago (AWS_DEFAULT_REGION)
    dataset_region: str  # región del bucket del reto (otra cuenta y otra región que el lago)
    work_dir: str  # scratch local (warehouse.duckdb, target/, logs, staging de publicación)

    @classmethod
    def from_env(cls) -> Settings:
        root = os.environ.get("PIPELINE_ROOT", "data").rstrip("/")
        return cls(
            root=root,
            dataset_bucket=os.environ.get("DATASET_BUCKET", ""),
            dataset_prefix=os.environ.get("DATASET_PREFIX", "data/"),
            region=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
            dataset_region=os.environ.get("DATASET_REGION", "us-east-2"),
            work_dir=os.environ.get("WORK_DIR") or (root if not root.startswith("s3://") else "work"),
        )

    @property
    def is_remote(self) -> bool:
        return self.root.startswith("s3://")

    @property
    def warehouse_path(self) -> str:
        """DuckDB es un archivo local: aun con el lake en S3, el warehouse vive en el scratch."""
        return f"{self.work_dir}/warehouse.duckdb"

    @property
    def eval_path(self) -> str:
        """Base propia de la zona del evaluador (labels y timeline); nunca dentro del warehouse."""
        return f"{self.work_dir}/eval.duckdb"
