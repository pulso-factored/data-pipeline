"""Publicación de los marts gold como artefactos físicamente separados, con guardias que fallan cerrado.

Separar archivos (y, en producción, prefijos S3 con IAM distinto) es lo que impone la gobernanza; un
esquema llamado "restricted" dentro de un mismo .duckdb es solo una convención.

  publish/<run_id>/gold_analytics.duckdb + parquet/   seudonimizado; para análisis y ML
  publish/<run_id>/gold_masked.duckdb                 read-models por cliente con PII enmascarada (generado del catálogo)
  publish/<run_id>/gold_restricted.duckdb             PII en claro y clasificada; solo tools autenticadas
  publish/<run_id>/field_classification.json          catálogo para agent-core (--field-classifier)
  publish/<run_id>/read_model_contract.json           contrato de lectura de los read-models (grano, llaves, nulos, corte)
  publish/<run_id>/release.json                       lineage, hashes y calidad de esta publicación
  publish/latest.json                                 puntero; se escribe al final (conmutación atómica)

Nunca se publican: pseudonym_map (permite re-identificar), labels/timeline (zona del evaluador) ni bronze.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from pipeline.config import Settings
from pipeline.export_catalog import build as build_catalog
from pipeline.read_contract import ORDER_BY, build_contract, check_documented

ANALYTICS_SCHEMA = "gold_analytics"
RESTRICTED_SCHEMA = "gold_restricted"
MASKED_SCHEMA = "gold_masked"
NEVER_PUBLISH_TABLES = {"pseudonym_map"}
NEVER_PUBLISH_COLUMNS = {"labels", "final_status", "final_resolution_code", "final_resolution_date", "final_sla_breached"}


class PublishError(Exception):
    pass


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tables_of(con: duckdb.DuckDBPyConnection, schema: str) -> list[str]:
    return [r[0] for r in con.execute(
        "select table_name from information_schema.tables where table_schema = ? and table_type = 'BASE TABLE' "
        "order by 1", [schema]).fetchall()]


def check_guards(con: duckdb.DuckDBPyConnection, catalog: dict[str, dict[str, Any]]) -> None:
    """Falla cerrado: analytics sin PII directa, nada de labels y toda columna restringida clasificada."""
    direct = {k.split(".")[-1] for k, r in catalog.items() if r["field_class"] == "pii_direct"} - {"customer_pseudo"}
    for schema in (ANALYTICS_SCHEMA, MASKED_SCHEMA):
        for t in tables_of(con, schema):
            cols = {r[0] for r in con.execute(
                "select column_name from information_schema.columns where table_schema = ? and table_name = ?",
                [schema, t]).fetchall()}
            leaked = cols & direct
            if leaked:
                raise PublishError(f"{schema}.{t} contiene PII directa: {sorted(leaked)}")
    for schema in (ANALYTICS_SCHEMA, MASKED_SCHEMA, RESTRICTED_SCHEMA):
        for t in tables_of(con, schema):
            if t in NEVER_PUBLISH_TABLES:
                continue
            cols = [r[0] for r in con.execute(
                "select column_name from information_schema.columns where table_schema = ? and table_name = ?",
                [schema, t]).fetchall()]
            bad = set(cols) & NEVER_PUBLISH_COLUMNS
            if bad:
                raise PublishError(f"{schema}.{t} contiene campos del evaluador: {sorted(bad)}")
            if schema == RESTRICTED_SCHEMA:
                missing = [c for c in cols if f"{t}.{c}" not in catalog]
                if missing:
                    raise PublishError(f"{schema}.{t}: columnas sin clasificar {missing}")


def _copy_schema(
    src: duckdb.DuckDBPyConnection, db_path: Path, schema: str, parquet_dir: Path | None, subject: str | None = None
) -> dict[str, int]:
    """`subject`: si se da, las tablas con orden físico definido (ORDER_BY) se publican ordenadas por esa columna del
    sujeto, lo que acelera la consulta puntual por cliente. El orden es una optimización, no una garantía."""
    catalog = src.execute("select current_database()").fetchone()[0]  # el archivo puede llamarse como el esquema
    out = duckdb.connect(str(db_path))
    out.execute(f'create schema "{schema}"."{schema}"')
    rows: dict[str, int] = {}
    for t in tables_of(src, schema):
        if t in NEVER_PUBLISH_TABLES:
            continue
        order = f" order by {ORDER_BY[t].replace('customer_id', subject)}" if subject and t in ORDER_BY else ""
        df = src.execute(f'select * from "{catalog}"."{schema}"."{t}"{order}').to_arrow_table()
        out.register("tmp_t", df)
        out.execute(f'create table "{schema}"."{schema}"."{t}" as select * from tmp_t')
        out.unregister("tmp_t")
        rows[t] = df.num_rows
        if parquet_dir is not None:
            parquet_dir.mkdir(parents=True, exist_ok=True)
            out.execute(f"copy \"{schema}\".\"{schema}\".\"{t}\" to '{(parquet_dir / (t + '.parquet')).as_posix()}' (format parquet, compression zstd)")
    out.close()
    return rows


def publish(warehouse: Path, dest_root: Path, run_id: str | None = None) -> Path:
    run_id = run_id or f"run-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    catalog = build_catalog()
    src = duckdb.connect(str(warehouse), read_only=True)
    check_guards(src, catalog)

    # Antes de crear nada: un fallo aquí no debe dejar un directorio que bloquee el reintento (publicaciones inmutables).
    published_models = [t for z in (RESTRICTED_SCHEMA, MASKED_SCHEMA) for t in tables_of(src, z) if t not in NEVER_PUBLISH_TABLES]
    check_documented(published_models)

    out_dir = dest_root / "publish" / run_id
    if out_dir.exists():
        raise PublishError(f"{out_dir} ya existe: las publicaciones son inmutables")
    out_dir.mkdir(parents=True)

    analytics_rows = _copy_schema(src, out_dir / "gold_analytics.duckdb", ANALYTICS_SCHEMA, out_dir / "parquet")
    restricted_rows = _copy_schema(src, out_dir / "gold_restricted.duckdb", RESTRICTED_SCHEMA, None, "customer_id")
    masked_rows = _copy_schema(src, out_dir / "gold_masked.duckdb", MASKED_SCHEMA, None, "customer_pseudo")
    (out_dir / "field_classification.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    contract = build_contract(src, catalog, run_id, {"restricted": RESTRICTED_SCHEMA, "masked": MASKED_SCHEMA})
    (out_dir / "read_model_contract.json").write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")

    dq = src.execute(
        "select table_name, outcome, rows from gold_analytics.dq_quarantine where outcome <> 'valid' order by 1, 2"
    ).fetchall() if "dq_quarantine" in analytics_rows else []
    src.close()

    try:
        git_sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False,
                                 cwd=Path(__file__).resolve().parents[2]).stdout.strip() or None
    except OSError:
        git_sha = None
    artifacts = {p.name: sha256_of(p) for p in sorted(out_dir.glob("*")) if p.is_file()}
    artifacts.update({f"parquet/{p.name}": sha256_of(p) for p in sorted((out_dir / "parquet").glob("*.parquet"))})
    release = {
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "git_sha": git_sha,
        "contracts": {"platform_history": "0.5.1"},
        "rows": {ANALYTICS_SCHEMA: analytics_rows, MASKED_SCHEMA: masked_rows, RESTRICTED_SCHEMA: restricted_rows},
        "quarantine": [{"table": t, "reason": r, "rows": n} for t, r, n in dq],
        "never_published": sorted(NEVER_PUBLISH_TABLES) + ["labels", "timeline", "bronze"],
        "artifacts_sha256": artifacts,
    }
    (out_dir / "release.json").write_text(json.dumps(release, ensure_ascii=False, indent=2), encoding="utf-8")
    # Conmutación atómica del puntero: se escribe al final y por reemplazo.
    tmp = dest_root / "publish" / "latest.json.tmp"
    tmp.write_text(json.dumps({"run_id": run_id, "path": f"publish/{run_id}"}), encoding="utf-8")
    os.replace(tmp, dest_root / "publish" / "latest.json")
    return out_dir


EVAL_SCHEMA = "eval"
EVAL_AREA = "bronze_eval/eval"  # bajo el prefijo que el bucket ya reserva al evaluador


def publish_eval(eval_db: Path, dest_root: Path, run_id: str | None = None) -> Path:
    """Publica la base del evaluador (labels, timeline, replay_order) bajo bronze_eval/eval/<run_id>/.

    Va FUERA de publish/: los lectores de analytics, masked y restricted no deben poder leerla. Guardia: la base solo
    puede contener el esquema eval (nunca silver, canonical ni gold)."""
    run_id = run_id or f"eval-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    src = duckdb.connect(str(eval_db), read_only=True)
    schemas = {r[0] for r in src.execute(
        "select distinct table_schema from information_schema.tables "
        "where table_schema not in ('information_schema', 'pg_catalog')"
    ).fetchall()}
    if schemas != {EVAL_SCHEMA}:
        raise PublishError(f"La base del evaluador debe contener solo el esquema {EVAL_SCHEMA}; tiene {sorted(schemas)}")
    out_dir = dest_root / EVAL_AREA / run_id
    if out_dir.exists():
        raise PublishError(f"{out_dir} ya existe: las publicaciones son inmutables")
    out_dir.mkdir(parents=True)
    rows = _copy_schema(src, out_dir / "eval.duckdb", EVAL_SCHEMA, None)
    src.close()
    release = {
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "zone": "evaluator-only",
        "rows": {EVAL_SCHEMA: rows},
        "artifacts_sha256": {"eval.duckdb": sha256_of(out_dir / "eval.duckdb")},
    }
    (out_dir / "release.json").write_text(json.dumps(release, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp = dest_root / EVAL_AREA / "latest.json.tmp"
    tmp.write_text(json.dumps({"run_id": run_id, "path": f"{EVAL_AREA}/{run_id}"}), encoding="utf-8")
    os.replace(tmp, dest_root / EVAL_AREA / "latest.json")
    return out_dir


def publish_eval_from_settings(settings: Settings, run_id: str | None = None) -> str:
    stage = Path(settings.work_dir) if settings.is_remote else Path(settings.root)
    out = publish_eval(Path(settings.eval_path), stage, run_id)
    return upload_publication(out, settings.root, area=EVAL_AREA) if settings.is_remote else str(out)


def _split_s3(uri: str) -> tuple[str, str]:
    bucket, _, prefix = uri.removeprefix("s3://").partition("/")
    return bucket, prefix.strip("/")


def upload_publication(out_dir: Path, root_uri: str, client: Any = None, area: str = "publish") -> str:
    """Sube una publicación local a s3://.../publish/<run_id>/ y SOLO AL FINAL mueve latest.json.

    Las publicaciones son inmutables: si el prefijo del run ya tiene objetos, falla sin subir nada.
    Con S3_KMS_KEY_ID se cifra con esa clave (SSE-KMS); si no, vale el cifrado por defecto del bucket.
    """
    if client is None:
        import boto3

        client = boto3.client("s3")
    bucket, prefix = _split_s3(root_uri)
    run_id = out_dir.name
    base = f"{prefix}/{area}/{run_id}".lstrip("/")
    existing = client.list_objects_v2(Bucket=bucket, Prefix=f"{base}/", MaxKeys=1)
    if existing.get("KeyCount", 0):
        raise PublishError(f"s3://{bucket}/{base}/ ya existe: las publicaciones son inmutables")
    extra: dict[str, str] = {}
    if os.environ.get("S3_KMS_KEY_ID"):
        extra = {"ServerSideEncryption": "aws:kms", "SSEKMSKeyId": os.environ["S3_KMS_KEY_ID"]}
    for f in sorted(p for p in out_dir.rglob("*") if p.is_file()):
        client.upload_file(str(f), bucket, f"{base}/{f.relative_to(out_dir).as_posix()}", ExtraArgs=extra or None)
    latest = json.dumps({"run_id": run_id, "path": f"{area}/{run_id}"}).encode("utf-8")
    client.put_object(Bucket=bucket, Key=f"{prefix}/{area}/latest.json".lstrip("/"), Body=latest, **extra)
    return f"s3://{bucket}/{base}"


def publish_from_settings(settings: Settings, run_id: str | None = None) -> str:
    """Construye la publicación en el scratch y, si el lake es S3, la sube."""
    stage = Path(settings.work_dir) if settings.is_remote else Path(settings.root)
    out = publish(Path(settings.warehouse_path), stage, run_id)
    return upload_publication(out, settings.root) if settings.is_remote else str(out)


def main() -> None:
    p = argparse.ArgumentParser(description="Publica gold como artefactos separados")
    p.add_argument("--run-id")
    a = p.parse_args()
    print(f"publicado en {publish_from_settings(Settings.from_env(), a.run_id)}")


if __name__ == "__main__":
    main()

