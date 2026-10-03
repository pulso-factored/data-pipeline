"""Configuración del pipeline. Todo sale del entorno; nada de credenciales en código."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    root: str  # raíz del lakehouse: ruta local o s3://bucket/prefix
    dataset_bucket: str
    dataset_prefix: str
    region: str

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            root=os.environ.get("PIPELINE_ROOT", "data").rstrip("/"),
            dataset_bucket=os.environ.get("DATASET_BUCKET", ""),
            dataset_prefix=os.environ.get("DATASET_PREFIX", "data/"),
            region=os.environ.get("AWS_DEFAULT_REGION", "us-east-2"),
        )

    @property
    def is_remote(self) -> bool:
        return self.root.startswith("s3://")
