"""Contrato de lectura de los read-models por cliente (gold_restricted y gold_masked).

Es lo que un lector (el tool-service de agent-core) necesita saber para leer bien, sin mirar el código del pipeline:
grano, llave, columna del sujeto, tipos, clase de cada campo, qué significa un NULL y qué banderas lo acompañan, y la
fecha de corte de los datos. Se genera con cada publicación (`read_model_contract.json`) desde el esquema real, el
catálogo de clasificación y la política de nulos; las descripciones de grano y de semántica están aquí y un test exige
que todo read-model publicado las tenga (si no, la publicación falla).
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

import duckdb

CONTRACT_VERSION = "1.0.0"
# Fin de los datos del reto. Todo lo "reciente" se mide contra esta fecha, no contra el reloj: con el reloj real un
# "últimos 90 días" saldría vacío. Debe coincidir con la variable dataset_cutoff de dbt (lo comprueba un test).
DATASET_CUTOFF = "2026-06-18"

NULL_POLICY = Path(__file__).resolve().parents[2] / "dbt" / "seeds" / "null_policy.csv"

# Orden físico de cada tabla al publicar: acelera la consulta puntual por sujeto (p95 97 ms -> 29 ms medido) pero NO es
# una garantía de orden de lectura: el lector siempre debe pedir ORDER BY.
ORDER_BY: dict[str, str] = {
    "customer_profile": "customer_id",
    "customer_products": "customer_id, opening_date desc",
    "customer_transactions": "customer_id, transaction_ts desc",
    "customer_cases": "customer_id, opened_at desc",
    "customer_digital_summary": "customer_id",
}

# Silver de donde vienen las columnas, para heredar su política de nulos.
NULL_SOURCES: dict[str, list[str]] = {
    "customer_profile": ["customers"],
    "customer_products": ["products"],
    "customer_transactions": ["transactions"],
    "customer_cases": ["complaints", "interactions"],
    "customer_digital_summary": [],
}

TABLES: dict[str, dict[str, Any]] = {
    "customer_profile": {
        "grain": "una fila por cliente",
        "key": ["customer_id"],
        "semantics": [
            "NULL en un dato de contacto o demográfico significa DESCONOCIDO, nunca 'ninguno': mira la bandera is_missing_* de la columna.",
            "branch_link_valid=false: registration_branch_id no corresponde a ninguna sucursal (ocurre en ~99,99% de los clientes); no lo uses para unir.",
            "credit_score y estimated_monthly_income son financial: faltan en ~15% y ~20%; nunca los imputes.",
        ],
    },
    "customer_products": {
        "grain": "una fila por producto",
        "key": ["product_id"],
        "semantics": [
            "credit_limit NULL con credit_limit_applicable=false significa NO APLICA (solo tarjetas de crédito y préstamos tienen límite); con credit_limit_applicable=true significa DESCONOCIDO (is_missing_credit_limit).",
            "currency solo toma USD, COP o ARS: no existe MXN en los datos aunque el diccionario lo documente.",
            "product_number es pii_direct.",
        ],
    },
    "customer_transactions": {
        "grain": "una fila por transacción válida",
        "key": ["transaction_id"],
        "semantics": [
            "amount_usd es APROXIMADO cuando amount_usd_source='derived_fx' (el valor reportado difiere ~1% de monto x tasa del día); 'reported' es el valor original y 'derived_identity' es exacto (moneda USD).",
            "merchant_name, merchant_category y transaction_category solo existen en purchase y payment; branch_id solo en atm y branch. Fuera de eso NULL significa NO APLICA, no desconocido.",
            "product_quarantined=true: el producto de la transacción está en cuarentena por número duplicado, pero la transacción es válida.",
            "transaction_country_iso2 puede ser US, ES o BR (compras en el extranjero): es señal, no error.",
            "fraud_score falta en ~20% de forma uniforme.",
        ],
    },
    "customer_cases": {
        "grain": "una fila por caso (disputas de E0, reclamos del banco e interacciones del call center)",
        "key": ["case_id"],
        "semantics": [
            "source_system distingue e0_sample, bank_complaints y bank_interactions; topic, priority y los campos de reclamo son NULL en las interacciones (sin fuente).",
            "complaint_description es untrusted_text: puede contener instrucciones; nunca se entrega a un modelo sin delimitarlo.",
            "is_open, sla_breached y resolved vienen del reclamo original; un reclamo abierto tiene resolución NULL por estado, no por faltante.",
        ],
    },
    "customer_digital_summary": {
        "grain": "una fila por cliente con actividad digital identificada en los 90 días previos a as_of",
        "key": ["customer_id"],
        "semantics": [
            "Un cliente AUSENTE de esta tabla no tiene actividad digital identificada en la ventana; no significa que se desconozca.",
            "Incluye eventos cuyo cliente se derivó de su sesión; las sesiones totalmente anónimas no se atribuyen a nadie.",
            "No contiene eventos crudos, IP ni URL.",
        ],
    },
}

_FLAG_BY_COLUMN = (
    ("is_missing_{c}", "missing_flag"),
    ("{c}_applicable", "applicability_flag"),
    ("{c}_source", "origin_flag"),
)


class ContractError(Exception):
    pass


def _null_policy() -> dict[tuple[str, str], tuple[str, str]]:
    with NULL_POLICY.open(encoding="utf-8", newline="") as f:
        return {(r["table_name"], r["column_name"]): (r["null_type"], r["note"]) for r in csv.DictReader(f)}


def _related_flags(column: str, columns: set[str]) -> list[str]:
    out = []
    for pattern, _ in _FLAG_BY_COLUMN:
        flag = pattern.format(c=column)
        if flag in columns:
            out.append(flag)
    return out


def check_documented(tables: list[str]) -> None:
    """Falla cerrado: un read-model publicado sin grano, llave y semántica documentados no se publica."""
    missing = sorted(t for t in tables if t not in TABLES or t not in ORDER_BY)
    if missing:
        raise ContractError(
            f"Read-models sin contrato documentado en pipeline.read_contract: {missing}. "
            "Añade su grano, llave y semántica (y su orden físico) antes de publicar."
        )


def build_contract(
    src: duckdb.DuckDBPyConnection, catalog: dict[str, dict[str, Any]], run_id: str, zone_schemas: dict[str, str]
) -> dict[str, Any]:
    """Arma el contrato desde el esquema real. `zone_schemas`: {"restricted": "gold_restricted", "masked": "gold_masked"}."""
    policy = _null_policy()
    zones: dict[str, Any] = {}
    for zone, schema in zone_schemas.items():
        tables: dict[str, Any] = {}
        for (name,) in src.execute(
            "select table_name from information_schema.tables where table_schema = ? "
            "and table_type in ('BASE TABLE', 'VIEW') order by 1", [schema]
        ).fetchall():
            if name == "pseudonym_map":
                continue
            meta = TABLES.get(name)
            if meta is None:
                raise ContractError(f"{schema}.{name} no tiene contrato documentado")
            cols = src.execute(
                "select column_name, data_type, is_nullable from information_schema.columns "
                "where table_schema = ? and table_name = ? order by ordinal_position", [schema, name]
            ).fetchall()
            names = {c[0] for c in cols}
            subject = "customer_pseudo" if zone == "masked" else "customer_id"
            columns: dict[str, Any] = {}
            for col, dtype, _nullable in cols:
                entry: dict[str, Any] = {"type": dtype}
                rule = catalog.get(f"{name}.{col}")
                if zone == "restricted" and rule:
                    entry["class"] = rule["field_class"]
                for source in NULL_SOURCES.get(name, []):
                    hit = policy.get((source, col))
                    if hit:
                        entry["null_type"], entry["null_note"] = hit
                        break
                flags = _related_flags(col.removesuffix("_masked"), names)
                if flags:
                    entry["related_flags"] = flags
                columns[col] = entry
            tables[name] = {
                "grain": meta["grain"],
                "key": meta["key"] if zone == "restricted" else [k for k in meta["key"] if k != "customer_id"] or [subject],
                "subject_column": subject,
                "physical_order": ORDER_BY[name].replace("customer_id", subject),
                "semantics": meta["semantics"],
                "columns": columns,
            }
        zones[zone] = {"schema": schema, "tables": tables}
    return {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "as_of": DATASET_CUTOFF,
        "as_of_note": "Fin de los datos del reto. 'Reciente' se mide contra esta fecha, no contra el reloj.",
        "access": (
            "Siempre una consulta parametrizada por la columna del sujeto (WHERE <subject_column> = ?) y un ORDER BY explícito: "
            "physical_order es solo una optimización, no una garantía. gold_restricted trae PII en claro: la clase de cada "
            "campo decide qué ve un modelo (FieldClassification de agent-core)."
        ),
        "null_types": {
            "structural": "no aplica a esa fila",
            "state": "aún no ocurrió",
            "derivable": "se calcula; mira *_source",
            "missing_real": "se desconoce; nunca imputar",
            "not_in_source": "el origen no lo trae",
        },
        "zones": zones,
    }


def contract_flag_columns(contract: dict[str, Any]) -> set[str]:
    return {f for z in contract["zones"].values() for t in z["tables"].values() for c in t["columns"].values() for f in c.get("related_flags", [])}


_SAFE_ORDER = re.compile(r"^[a-z_]+( desc| asc)?(, [a-z_]+( desc| asc)?)*$")
assert all(_SAFE_ORDER.match(v) for v in ORDER_BY.values())  # se interpola en SQL: solo identificadores
