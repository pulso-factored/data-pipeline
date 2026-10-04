"""Genera dbt/seeds/field_classification.csv: clase de cada columna expuesta, según el ADR 0008 de agent-core
(pii_direct | pii_quasi | financial | untrusted_text | public). Una columna sin clasificar se trata como
pii_direct; el test field_classification_coverage obliga a que toda columna expuesta esté aquí."""

from __future__ import annotations

import csv
import os
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
WAREHOUSE = Path(os.environ.get("PIPELINE_ROOT", ROOT / "data")) / "warehouse.duckdb"

PII_DIRECT = {
    "customer_id", "source_customer_id", "document_number", "phone", "employee_code", "ip_address", "customer_id_resolved", "first_name", "last_name", "email",
    "mobile_phone", "landline_phone", "address", "product_number", "customer_pseudo",
}
PII_QUASI = {
    "date_of_birth", "gender", "city", "state", "postal_code", "transaction_city", "latitude",
    "longitude", "occupation", "marital_status", "education_level", "registration_date",
    "detected_accent", "assigned_analyst_id", "assigned_agent_id", "actor_id", "analyst_id",
    "author_id", "requested_by_id", "decided_by", "branch_id", "opening_branch_id", "agent_id",
    "customer_detected_accent", "agent_used_accent", "native_accent", "country_of_origin_iso2", "hire_date",
    "session_id", "ip_country", "ip_city", "open_country",
    "registration_branch_id", "related_branch_id",
}
FINANCIAL = {
    "credit_score", "estimated_monthly_income", "current_balance", "credit_limit", "interest_rate",
    "days_past_due", "amount", "amount_usd", "amount_usd_reported", "claimed_amount",
    "compensation_granted", "fraud_score", "is_fraud", "conversion_value", "event_value", "send_cost", "budget",
}
UNTRUSTED = {
    "description", "complaint_description", "resolution", "text", "question_text", "answer",
    "decision_note", "requester_note", "full_text", "customer_text", "agent_text", "mentioned_entities",
    "detected_keywords", "open_comments",
}
# Tags de los tokens (⟦tag:n⟧) y generalización de pii_quasi, según agent_core.views.classification.
TAGS = {
    "first_name": "name", "last_name": "name", "document_number": "doc", "email": "email",
    "mobile_phone": "tel", "landline_phone": "tel", "address": "addr", "product_number": "prod",
    "customer_id": "cus", "source_customer_id": "cus", "customer_pseudo": "cus",
    "phone": "tel", "employee_code": "emp", "ip_address": "ip", "customer_id_resolved": "cus",
}
QUASI_RULES = {"date_of_birth": ("age_bucket", 10)}  # el resto de pii_quasi se elimina (drop)
SCOPE = [("silver", t) for t in (
    "customers", "products", "complaints", "transactions", "exchange_rates", "service_agents", "interactions",
    "call_transcripts", "satisfaction_surveys", "campaign_sends", "digital_events")]


def classify(column: str) -> str:
    if column in UNTRUSTED:
        return "untrusted_text"
    if column in PII_DIRECT:
        return "pii_direct"
    if column in FINANCIAL:
        return "financial"
    if column in PII_QUASI:
        return "pii_quasi"
    return "public"


def main() -> None:
    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    tables = list(SCOPE)
    for schema in ("canonical", "gold_restricted"):
        for (t,) in con.execute(
            "select table_name from information_schema.tables where table_schema = ? "
            "and table_type = 'BASE TABLE' order by 1", [schema]
        ).fetchall():
            tables.append((schema, t))
    rows = []
    for schema, table in tables:
        for (col,) in con.execute(
            "select column_name from information_schema.columns where table_schema = ? and table_name = ? "
            "order by ordinal_position", [schema, table]
        ).fetchall():
            cls = classify(col)
            tag = TAGS.get(col, "pii") if cls == "pii_direct" else "none"
            qop, qwidth = (QUASI_RULES.get(col, ("drop", 10)) if cls == "pii_quasi" else ("none", 0))
            rows.append((schema, table, col, cls, tag, qop, qwidth))
    out = ROOT / "dbt" / "seeds" / "field_classification.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["schema_name", "table_name", "column_name", "class", "tag", "quasi_op", "quasi_width"])
        w.writerows(rows)
    by_class: dict[str, int] = {}
    for r in rows:
        by_class[r[3]] = by_class.get(r[3], 0) + 1
    print(f"{len(rows)} columnas en {len(tables)} tablas -> {by_class}")


if __name__ == "__main__":
    main()
