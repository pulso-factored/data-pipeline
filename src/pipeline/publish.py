"""Publicación de los marts gold como artefactos físicamente separados, con guardias que fallan cerrado.

Separar archivos (y, en producción, prefijos S3 con IAM distinto) es lo que impone la gobernanza; un
esquema llamado "restricted" dentro de un mismo .duckdb es solo una convención.

  publish/<run_id>/gold_analytics.duckdb + parquet/   seudonimizado; para análisis y ML
  publish/<run_id>/gold_masked.duckdb                 read-models por cliente con PII enmascarada (generado del catálogo)
  publish/<run_id>/gold_restricted.duckdb             PII en claro y clasificada; solo tools autenticadas
  publish/<run_id>/field_classification.json          catálogo para agent-core (--field-classifier)
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


def _copy_schema(src: duckdb.DuckDBPyConnection, db_path: Path, schema: str, parquet_dir: Path | None) -> dict[str, int]:
    out = duckdb.connect(str(db_path))
    out.execute(f'create schema "{schema}"."{schema}"')
    rows: dict[str, int] = {}
    for t in tables_of(src, schema):
        if t in NEVER_PUBLISH_TABLES:
            continue
        df = src.execute(f'select * from "{schema}"."{t}"').to_arrow_table()
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

    out_dir = dest_root / "publish" / run_id
    if out_dir.exists():
        raise PublishError(f"{out_dir} ya existe: las publicaciones son inmutables")
    out_dir.mkdir(parents=True)

    analytics_rows = _copy_schema(src, out_dir / "gold_analytics.duckdb", ANALYTICS_SCHEMA, out_dir / "parquet")
    restricted_rows = _copy_schema(src, out_dir / "gold_restricted.duckdb", RESTRICTED_SCHEMA, None)
    masked_rows = _copy_schema(src, out_dir / "gold_masked.duckdb", MASKED_SCHEMA, None)
    (out_dir / "field_classification.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")

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


def main() -> None:
    p = argparse.ArgumentParser(description="Publica gold como artefactos separados")
    p.add_argument("--run-id")
    a = p.parse_args()
    settings = Settings.from_env()
    if settings.is_remote:
        raise SystemExit("Publicación a S3 pendiente: publicar local y subir con el runner de despliegue.")
    out = publish(Path(settings.root) / "warehouse.duckdb", Path(settings.root), a.run_id)
    print(f"publicado en {out}")


if __name__ == "__main__":
    main()

