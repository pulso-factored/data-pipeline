"""Subida de una publicación a S3 con un cliente simulado (sin red ni credenciales)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pipeline.publish import PublishError, upload_publication


class FakeS3:
    def __init__(self, existing: list[str] | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.existing = existing or []
        self.extra: list[Any] = []

    def list_objects_v2(self, Bucket: str, Prefix: str, MaxKeys: int) -> dict[str, int]:
        return {"KeyCount": sum(1 for k in self.existing if k.startswith(Prefix))}

    def upload_file(self, path: str, bucket: str, key: str, ExtraArgs: Any = None) -> None:
        self.calls.append(("upload", key))
        self.extra.append(ExtraArgs)

    def put_object(self, Bucket: str, Key: str, Body: bytes, **kw: Any) -> None:
        self.calls.append(("put", Key))
        self.extra.append(kw or None)


def _run_dir(tmp_path: Path) -> Path:
    d = tmp_path / "publish" / "run-1"
    (d / "parquet").mkdir(parents=True)
    for name in ("gold_analytics.duckdb", "release.json", "parquet/case_facts.parquet"):
        (d / name).write_bytes(b"x")
    return d


def test_pointer_moves_last_and_keys_are_under_the_run_prefix(tmp_path: Path) -> None:
    s3 = FakeS3()
    uri = upload_publication(_run_dir(tmp_path), "s3://lake/pulso", client=s3)
    assert uri == "s3://lake/pulso/publish/run-1"
    keys = [k for _, k in s3.calls]
    assert keys[-1] == "pulso/publish/latest.json"  # el puntero se conmuta al final
    assert all(k.startswith("pulso/publish/run-1/") for k in keys[:-1])
    assert "pulso/publish/run-1/parquet/case_facts.parquet" in keys


def test_existing_run_is_never_overwritten(tmp_path: Path) -> None:
    s3 = FakeS3(existing=["pulso/publish/run-1/release.json"])
    with pytest.raises(PublishError, match="inmutables"):
        upload_publication(_run_dir(tmp_path), "s3://lake/pulso", client=s3)
    assert s3.calls == []  # no subió nada ni movió el puntero


def test_kms_key_is_used_when_configured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("S3_KMS_KEY_ID", "arn:aws:kms:us-east-1:111111111111:key/abc")
    s3 = FakeS3()
    upload_publication(_run_dir(tmp_path), "s3://lake", client=s3)
    assert all(e and e["ServerSideEncryption"] == "aws:kms" for e in s3.extra)


def test_eval_area_uploads_under_bronze_eval_and_moves_its_own_pointer(tmp_path: Path) -> None:
    d = tmp_path / "bronze_eval" / "eval" / "eval-1"
    d.mkdir(parents=True)
    (d / "eval.duckdb").write_bytes(b"x")
    s3 = FakeS3()
    uri = upload_publication(d, "s3://lake/pulso", client=s3, area="bronze_eval/eval")
    keys = [k for _, k in s3.calls]
    assert uri == "s3://lake/pulso/bronze_eval/eval/eval-1"
    assert keys == ["pulso/bronze_eval/eval/eval-1/eval.duckdb", "pulso/bronze_eval/eval/latest.json"]
    assert not any("/publish/" in k for k in keys)  # jamás en el prefijo de los consumidores
