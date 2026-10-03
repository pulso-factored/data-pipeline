"""Verificación puntual de gold_masked contra gold_restricted (necesita acceso a ambos: corre en el pipeline).
No forma parte de los artefactos publicados. Falla con código 1 si encuentra una fuga."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
WAREHOUSE = Path(os.environ.get("PIPELINE_ROOT", ROOT / "data")) / "warehouse.duckdb"
DIRECT = ("customer_id", "first_name", "last_name", "document_number", "email", "mobile_phone",
          "landline_phone", "address", "product_number")
DROPPED = ("postal_code", "city", "state", "gender", "latitude", "longitude", "transaction_city",
           "opening_branch_id", "branch_id", "assigned_analyst_id")


def main() -> int:
    c = duckdb.connect(str(WAREHOUSE), read_only=True)

    def q(sql: str):
        return c.execute(sql).fetchall()

    problems: list[str] = []
    cols = {r[0] for r in q("select column_name from information_schema.columns where table_schema = 'gold_masked'")}
    for name in DIRECT + DROPPED:
        if name in cols:
            problems.append(f"gold_masked expone la columna {name}")

    for t in ("customer_profile", "customer_products", "customer_transactions", "customer_cases"):
        a, b = q(f"select count(*) from gold_masked.{t}")[0][0], q(f"select count(*) from gold_restricted.{t}")[0][0]
        if a != b:
            problems.append(f"{t}: {a} filas enmascaradas vs {b} restringidas")
    if q("select count(*) from gold_masked.customer_profile where customer_pseudo is null")[0][0]:
        problems.append("customer_profile: clientes sin seudónimo")

    # El valor enmascarado nunca debe contener el crudo completo.
    leaks = q("""
        select count(*) from gold_masked.customer_profile m
        join gold_restricted.pseudonym_map pm using (customer_pseudo)
        join gold_restricted.customer_profile r on r.customer_id = pm.customer_id
        where m.document_number_masked = r.document_number or m.email_masked = r.email
           or m.address_masked = r.address or m.first_name_masked = r.first_name
           or m.mobile_phone_masked = r.mobile_phone""")[0][0]
    if leaks:
        problems.append(f"{leaks} filas con un valor enmascarado igual al crudo")

    # La mitad oculta de los documentos no puede aparecer: solo los últimos 4 dígitos.
    long_doc = q("select count(*) from gold_masked.customer_profile where length(document_number_masked) > 7")[0][0]
    if long_doc:
        problems.append(f"{long_doc} documentos enmascarados con más de 4 caracteres visibles")

    print("columnas de gold_masked.customer_profile:", sorted(r[0] for r in q("describe gold_masked.customer_profile")))
    print("muestra:", q("select first_name_masked, document_number_masked, email_masked, mobile_phone_masked, age_bucket from gold_masked.customer_profile limit 2"))
    print("descripción de reclamo:", q("select complaint_description from gold_masked.customer_cases limit 1"))
    if problems:
        print("FUGAS:", *problems, sep="\n  - ")
        return 1
    print("OK: sin fugas detectadas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
