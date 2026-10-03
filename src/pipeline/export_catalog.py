"""Exporta el catálogo FieldClassification (seed) al formato que consume agent-core (`FieldClassifier`).

Formato: {"<tabla>.<campo>" | "<campo>": {"field_class", "tag", "quasi": {"op", "width"}}}.
- Se emite una entrada por ruta `tabla.campo` (agent-core busca primero la ruta exacta).
- Se emite el nombre de campo sin tabla solo si TODAS sus apariciones tienen la misma regla; si no,
  se omite y las rutas explícitas mandan (lo no resuelto cae en pii_direct, el lado seguro).
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

SEED = Path(__file__).resolve().parents[2] / "dbt" / "seeds" / "field_classification.csv"
FIELD_CLASSES = {"pii_direct", "pii_quasi", "financial", "untrusted_text", "public"}


def _rule(row: dict[str, str]) -> dict[str, Any]:
    rule: dict[str, Any] = {"field_class": row["class"]}
    if row["class"] == "pii_direct":
        rule["tag"] = row["tag"] if row["tag"] not in ("", "none") else "pii"
    if row["class"] == "pii_quasi":
        rule["quasi"] = {"op": row["quasi_op"] if row["quasi_op"] not in ("", "none") else "drop", "width": int(row["quasi_width"] or 10) or 10}
    return rule


def build(seed: Path = SEED) -> dict[str, dict[str, Any]]:
    with seed.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    catalog: dict[str, dict[str, Any]] = {}
    by_field: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        if r["class"] not in FIELD_CLASSES:
            raise ValueError(f"clase inválida {r['class']!r} en {r['table_name']}.{r['column_name']}")
        rule = _rule(r)
        catalog[f"{r['table_name']}.{r['column_name']}"] = rule
        by_field.setdefault(r["column_name"], []).append(rule)
    for field, rules in by_field.items():
        if all(x == rules[0] for x in rules):
            catalog[field] = rules[0]
    return dict(sorted(catalog.items()))


def main() -> None:
    p = argparse.ArgumentParser(description="Exporta field_classification.json para agent-core")
    p.add_argument("--out", default="field_classification.json")
    a = p.parse_args()
    catalog = build()
    Path(a.out).write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(catalog)} entradas -> {a.out}")


if __name__ == "__main__":
    main()
