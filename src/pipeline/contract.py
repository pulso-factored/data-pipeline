"""Validación de una tabla parquet contra una entidad de un contrato JSON (platform_history).

Se valida lo que el contrato afirma de forma verificable: columnas obligatorias presentes,
obligatorios sin nulos y valores dentro del dominio. Los tipos no se comparan estrictamente
porque los arreglos y JSON del contrato llegan serializados como VARCHAR en el parquet.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb


class ContractError(Exception):
    pass


def load_contract(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_entity(
    con: duckdb.DuckDBPyConnection, parquet_path: str, entity: str, contract: dict[str, Any]
) -> list[str]:
    fields = contract["entities"][entity]["fields"]
    present = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{parquet_path}')").fetchall()}
    problems: list[str] = []
    for name, spec in fields.items():
        if name not in present:
            if spec.get("required"):
                problems.append(f"{entity}.{name}: columna obligatoria ausente")
            continue
        if spec.get("required"):
            nulls = con.execute(
                f'SELECT count(*) FROM read_parquet(\'{parquet_path}\') WHERE "{name}" IS NULL'
            ).fetchone()[0]
            if nulls:
                problems.append(f"{entity}.{name}: {nulls} nulos en campo obligatorio")
        domain = spec.get("domain")
        if domain and spec.get("type") in ("VARCHAR", "INTEGER"):
            if spec["type"] == "INTEGER":  # puede llegar como DOUBLE (1.0): comparar por valor
                col, vals = f'CAST("{name}" AS DOUBLE)', ", ".join(str(float(v)) for v in domain)
            else:
                col, vals = f'CAST("{name}" AS VARCHAR)', ", ".join(
                    "'" + str(v).replace("'", "''") + "'" for v in domain
                )
            bad = con.execute(
                f"SELECT count(*) FROM read_parquet('{parquet_path}') "
                f'WHERE "{name}" IS NOT NULL AND {col} NOT IN ({vals})'
            ).fetchone()[0]
            if bad:
                problems.append(f"{entity}.{name}: {bad} valores fuera de dominio")
    return problems
