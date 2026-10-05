"""Ingesta bronze del dataset del banco (S3 del reto) con carga incremental por etag.

Bronze es copia fiel: todo en VARCHAR, más metadatos de lineage. Una partición se
reingesta solo si es nueva o si cambió su etag (llegada tardía o corrección).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import uuid
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

import boto3
import duckdb
import pyarrow as pa

from pipeline.config import Settings, bound_duckdb

DIMENSIONS = (
    "customers",
    "products",
    "branches",
    "service_agents",
    "marketing_campaigns",
    "daily_exchange_rates",
)
FACTS = (
    "transactions",
    "call_center_interactions",
    "call_transcripts",
    "satisfaction_surveys",
    "digital_events",
    "complaints",
    "campaign_sends",
)
ALL_TABLES = DIMENSIONS + FACTS


def schema_hash(columns: list[str]) -> str:
    return hashlib.md5("|".join(columns).encode("utf-8")).hexdigest()


def relative_output(key: str, prefix: str) -> str:
    """`data/complaints/year=2023/.../x.csv` -> `complaints/year=2023/.../x.parquet`."""
    rel = key.removeprefix(prefix)
    return re.sub(r"\.csv$", ".parquet", rel)


def table_of(key: str, prefix: str) -> str:
    rel = key.removeprefix(prefix)
    head = rel.split("/")[0]
    return re.sub(r"\.csv$", "", head)


def needs_ingest(obj: dict[str, Any], seen: dict[str, str]) -> str | None:
    """Devuelve 'new', 'changed' o None si la partición ya está al día."""
    prev = seen.get(obj["key"])
    if prev is None:
        return "new"
    return None if prev == obj["etag"] else "changed"


def dataset_credentials(env: Mapping[str, str] | None = None) -> tuple[str, str] | None:
    """Credenciales propias del bucket del reto (DATASET_AWS_*), separadas de las del lago.

    AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY tienen prioridad sobre el rol de la tarea: si se usaran para el
    dataset, el pipeline escribiría en el lago con claves de solo lectura de otra cuenta. Sin DATASET_AWS_*,
    el dataset usa la cadena estándar (desarrollo local con las claves del reto en el entorno).
    """
    env = os.environ if env is None else env
    key, secret = env.get("DATASET_AWS_ACCESS_KEY_ID"), env.get("DATASET_AWS_SECRET_ACCESS_KEY")
    return (key, secret) if key and secret else None


def _sql_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def secret_statements(settings: Settings, creds: tuple[str, str] | None) -> list[str]:
    """Dos secretos de DuckDB: el lago (cadena estándar, su región) y el dataset (su credencial, su región,
    acotado por prefijo al bucket del reto; DuckDB usa el secreto de alcance más largo)."""
    # El secreto de cadena solo se crea con el lago en S3: sin credenciales la validación del secreto falla.
    lake = (
        [f"CREATE OR REPLACE SECRET lake (TYPE s3, PROVIDER credential_chain, REGION {_sql_str(settings.region)})"]
        if settings.is_remote else []
    )
    scope = _sql_str(f"s3://{settings.dataset_bucket}/")
    if creds:
        dataset = (
            f"CREATE OR REPLACE SECRET dataset (TYPE s3, KEY_ID {_sql_str(creds[0])}, SECRET {_sql_str(creds[1])}, "
            f"REGION {_sql_str(settings.dataset_region)}, SCOPE {scope})"
        )
    else:
        dataset = (
            f"CREATE OR REPLACE SECRET dataset (TYPE s3, PROVIDER credential_chain, "
            f"REGION {_sql_str(settings.dataset_region)}, SCOPE {scope})"
        )
    return [*lake, dataset]


def _connect(settings: Settings) -> duckdb.DuckDBPyConnection:
    con = bound_duckdb(duckdb.connect())
    con.execute("INSTALL httpfs; LOAD httpfs;")
    try:
        for statement in secret_statements(settings, dataset_credentials()):
            con.execute(statement)
    except duckdb.Error as exc:
        # El mensaje de DuckDB puede citar la sentencia: no se reenvía. Solo se dice qué falta.
        raise SystemExit(
            "No se pudieron crear las credenciales de S3. Defina DATASET_AWS_ACCESS_KEY_ID y "
            "DATASET_AWS_SECRET_ACCESS_KEY (bucket del reto) y, si el lago es s3://, un rol o credenciales "
            f"estándar de AWS ({type(exc).__name__})."
        ) from None
    return con


def _dataset_client(settings: Settings) -> Any:
    creds = dataset_credentials()
    kwargs: dict[str, Any] = {"region_name": settings.dataset_region}
    if creds:
        kwargs.update(aws_access_key_id=creds[0], aws_secret_access_key=creds[1])
    return boto3.client("s3", **kwargs)


def _list_objects(settings: Settings, tables: tuple[str, ...]) -> list[dict[str, Any]]:
    s3 = _dataset_client(settings)
    out: list[dict[str, Any]] = []
    for page in s3.get_paginator("list_objects_v2").paginate(
        Bucket=settings.dataset_bucket, Prefix=settings.dataset_prefix
    ):
        for o in page.get("Contents", []):
            key = o["Key"]
            if not key.endswith(".csv"):
                continue
            if table_of(key, settings.dataset_prefix) in tables:
                out.append(
                    {
                        "key": key,
                        "etag": o["ETag"].strip('"'),
                        "size": o["Size"],
                        "last_modified": o["LastModified"].astimezone(UTC).replace(tzinfo=None),
                    }
                )
    return sorted(out, key=lambda o: o["key"])


def _manifest_path(settings: Settings) -> str:
    return f"{settings.root}/bronze/_manifest/bank.parquet"


def _load_manifest(con: duckdb.DuckDBPyConnection, settings: Settings) -> dict[str, str]:
    path = _manifest_path(settings)
    try:
        rows = con.execute(f"SELECT key, etag FROM read_parquet('{path}')").fetchall()
    except duckdb.IOException:
        return {}
    return {k: e for k, e in rows}


def _save_manifest(
    con: duckdb.DuckDBPyConnection, settings: Settings, entries: dict[str, dict[str, Any]]
) -> None:
    path = _manifest_path(settings)
    if not settings.is_remote:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    table = pa.Table.from_pylist(list(entries.values()))
    con.register("manifest_new", table)
    con.execute(f"COPY (SELECT * FROM manifest_new ORDER BY key) TO '{path}' (FORMAT parquet)")
    con.unregister("manifest_new")


def _ingest_one(
    settings: Settings, obj: dict[str, Any], batch_id: str, reason: str
) -> dict[str, Any]:
    con = _connect(settings)
    src = f"s3://{settings.dataset_bucket}/{obj['key']}"
    out = f"{settings.root}/bronze/bank/{relative_output(obj['key'], settings.dataset_prefix)}"
    if not settings.is_remote:
        os.makedirs(os.path.dirname(out), exist_ok=True)
    read = f"read_csv('{src}', all_varchar=true, header=true, hive_partitioning=false)"
    cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {read}").fetchall()]
    shash = schema_hash(cols)
    con.execute(
        f"""COPY (
              SELECT *,
                     '{batch_id}' AS _batch_id,
                     '{obj['key']}' AS _source_file,
                     '{obj['etag']}' AS _source_etag,
                     TIMESTAMP '{datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}' AS _ingested_at,
                     '{shash}' AS _schema_hash
              FROM {read}
            ) TO '{out}' (FORMAT parquet, COMPRESSION zstd)"""
    )
    rows = con.execute(f"SELECT count(*) FROM read_parquet('{out}')").fetchone()[0]
    con.close()
    return {**obj, "batch_id": batch_id, "rows": rows, "schema_hash": shash, "reason": reason}


def run(tables: tuple[str, ...], workers: int = 8, limit: int | None = None) -> dict[str, int]:
    settings = Settings.from_env()
    if not settings.dataset_bucket:
        raise SystemExit("Falta DATASET_BUCKET en el entorno.")
    con = _connect(settings)
    seen = _load_manifest(con, settings)
    objects = _list_objects(settings, tables)
    todo = [(o, r) for o in objects if (r := needs_ingest(o, seen))]
    if limit:
        todo = todo[:limit]
    batch_id = f"b{datetime.now(UTC):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"

    entries: dict[str, dict[str, Any]] = {}
    previous = con.execute(f"SELECT * FROM read_parquet('{_manifest_path(settings)}')").fetchall() \
        if seen else []
    cols = ["key", "etag", "size", "last_modified", "batch_id", "rows", "schema_hash"]
    for row in previous:
        d = dict(zip([c[0] for c in con.description], row))
        entries[d["key"]] = {c: d[c] for c in cols}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_ingest_one, settings, o, batch_id, r) for o, r in todo]
        for f in futures:
            res = f.result()
            entries[res["key"]] = {c: res[c] for c in cols}
    if todo:
        _save_manifest(con, settings, entries)

    summary = {"listed": len(objects), "ingested": len(todo), "skipped": len(objects) - len(todo)}
    print(f"batch={batch_id} {summary}")
    return summary


def main() -> None:
    p = argparse.ArgumentParser(description="Ingesta bronze del dataset del banco")
    p.add_argument("--tables", default=",".join(ALL_TABLES))
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--limit", type=int, default=None, help="máx. archivos (pruebas)")
    a = p.parse_args()
    tables = tuple(t.strip() for t in a.tables.split(",") if t.strip())
    unknown = set(tables) - set(ALL_TABLES)
    if unknown:
        raise SystemExit(f"Tablas desconocidas: {sorted(unknown)}")
    run(tables, a.workers, a.limit)


if __name__ == "__main__":
    main()
