"""Ingesta bronze de la muestra E0 (snapshot estático y versionado por sha256).

- Valida cada tabla contra platform_history.json; si el contrato se rompe, la carga falla.
- `labels` y `timeline` (respuestas del evaluador) van a una ubicación física distinta
  (`bronze_eval/`), pensada para permisos separados. Nunca se mezclan con bronze.
- Solo para participantes del hackatón: no se publica ni se envía a servicios externos.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from pipeline.config import Settings, bound_duckdb
from pipeline.contract import ContractError, load_contract, validate_entity

HISTORY_TABLES = (
    "case", "turn", "identity_check", "routing_step", "copilot_query",
    "tool_call", "approval", "case_close", "signal",
)
EVAL_TABLES = ("labels", "timeline")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _out(settings: Settings, table: str) -> str:
    area = "bronze_eval" if table in EVAL_TABLES else "bronze"
    return f"{settings.root}/{area}/e0/{table}.parquet"


def run(source_dir: Path, force: bool = False) -> dict[str, str]:
    settings = Settings.from_env()
    datos, contratos = source_dir / "datos", source_dir / "contratos"
    history = load_contract(contratos / "platform_history.json")
    version = history["version"]
    manifest_path = f"{settings.root}/bronze/_manifest/e0.parquet"
    con = bound_duckdb(duckdb.connect())

    try:
        prev = {r[0]: r for r in con.execute(f"SELECT * FROM read_parquet('{manifest_path}')").fetchall()}
    except duckdb.IOException:
        prev = {}

    batch_id = f"e0-{datetime.now(UTC):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"
    results: dict[str, str] = {}
    rows_out: list[tuple] = []
    for table in HISTORY_TABLES + EVAL_TABLES:
        src = datos / f"{table}.parquet"
        digest = sha256_of(src)
        if not force and table in prev and prev[table][1] == digest:
            results[table] = "unchanged"
            rows_out.append(prev[table])
            continue
        if table in HISTORY_TABLES:
            problems = validate_entity(con, src.as_posix(), table, history)
            if problems:
                raise ContractError("; ".join(problems))
        out = _out(settings, table)
        if not settings.is_remote:
            os.makedirs(os.path.dirname(out), exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        con.execute(
            f"""COPY (SELECT *, '{batch_id}' AS _batch_id, '{digest}' AS _source_sha256,
                       '{version}' AS _contract_version, TIMESTAMP '{ts}' AS _ingested_at
                FROM read_parquet('{src.as_posix()}')) TO '{out}' (FORMAT parquet, COMPRESSION zstd)"""
        )
        n = con.execute(f"SELECT count(*) FROM read_parquet('{out}')").fetchone()[0]
        results[table] = f"loaded:{n}"
        rows_out.append((table, digest, n, version, batch_id))

    os.makedirs(os.path.dirname(manifest_path), exist_ok=True) if not settings.is_remote else None
    con.execute("CREATE TABLE m(table_name VARCHAR, sha256 VARCHAR, rows BIGINT, contract_version VARCHAR, batch_id VARCHAR)")
    con.executemany("INSERT INTO m VALUES (?,?,?,?,?)", rows_out)
    con.execute(f"COPY m TO '{manifest_path}' (FORMAT parquet)")
    print(f"batch={batch_id} contract=platform_history@{version} {results}")
    return results


def main() -> None:
    p = argparse.ArgumentParser(description="Ingesta bronze de la muestra E0")
    p.add_argument("--source", default=os.environ.get("E0_SOURCE_DIR"), help="carpeta con datos/ y contratos/")
    p.add_argument("--force", action="store_true")
    a = p.parse_args()
    if not a.source:
        raise SystemExit("Indica --source o E0_SOURCE_DIR (carpeta con datos/ y contratos/).")
    run(Path(a.source), a.force)


if __name__ == "__main__":
    main()
