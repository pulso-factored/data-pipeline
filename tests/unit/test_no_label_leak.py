"""Guarda anti-fuga: `labels`/`timeline` (respuestas del evaluador) y los campos `final_*` solo pueden
aparecer en la zona del evaluador (dbt/models/eval/). Si alguien los referencia en bronze, silver,
canonical o gold, este test falla antes de que lleguen a un consumidor."""

from __future__ import annotations

import re
from pathlib import Path

DBT = Path(__file__).resolve().parents[2] / "dbt"
EVAL_ZONE = DBT / "models" / "eval"
FORBIDDEN = re.compile(r"bronze_eval|\blabels\b|\bfinal_(status|resolution_code|resolution_date|sla_breached)\b")


def _files():
    for ext in ("*.sql", "*.yml"):
        for p in DBT.rglob(ext):
            if "target" in p.parts or "dbt_packages" in p.parts:
                continue
            if EVAL_ZONE in p.parents:
                continue
            yield p


def test_labels_never_referenced_outside_eval_zone() -> None:
    offenders = []
    for p in _files():
        text = p.read_text(encoding="utf-8")
        # Se ignoran líneas de comentario SQL/Jinja/YAML que solo documentan la regla.
        code = "\n".join(
            line for line in text.splitlines() if not line.strip().startswith(("--", "#"))
        )
        code = re.sub(r"\{#.*?#\}", "", code, flags=re.S)
        if FORBIDDEN.search(code):
            offenders.append(str(p.relative_to(DBT)))
    assert not offenders, f"Referencias a labels/final_* fuera de models/eval: {offenders}"
