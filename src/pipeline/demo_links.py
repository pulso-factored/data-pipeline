"""Vínculo clientes de la plataforma -> clientes del dataset (para demo y pruebas de extremo a extremo).

La plataforma (support-platform) inventa a propósito sus clientes de ejemplo: nunca copia registros del dataset. Por eso
el vínculo no puede ser por nombre; es una ASIGNACIÓN determinista de cada cliente de la plataforma a un cliente del
dataset que (1) coincida en país e idioma y (2) tenga datos ricos para que el asistente tenga qué leer: un producto
activo, movimientos y, de preferencia, una disputa de E0. Es una decisión de demostración, no una identidad real: en
producción el vínculo viene de la autenticación real del cliente (ADR 0004 de la plataforma).

Salida (privada, en `data/`, nunca al repo):
  bank-links.json          {"CUS-…": "<customer_id del dataset>"}   <- formato de CC_BANK_CUSTOMER_LINKS_FILE
  bank-links.report.json   por vínculo: coincidencias y cuánta data tiene (solo ids y conteos, sin PII)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from pipeline.config import Settings

CORE_PRODUCTS = ("credit_card", "debit_card", "checking_account", "savings_account")
MIN_TRANSACTIONS = 20


class LinkError(Exception):
    pass


@dataclass(frozen=True)
class Candidate:
    customer_id: str
    country_iso2: str
    active_core_products: int
    transactions: int
    e0_cases: int
    e0_pt_cases: int
    digital_sessions_90d: int


def _rank(platform_id: str, customer_id: str) -> str:
    """Orden estable e independiente del orden de entrada: mismo dataset + mismos clientes => mismos vínculos."""
    return hashlib.sha256(f"{platform_id}|{customer_id}".encode()).hexdigest()


def is_portuguese(locale: str) -> bool:
    return locale.lower().startswith("pt")


def _tier(c: Candidate, wants_pt: bool) -> int:
    """0 = ideal (con disputa de E0 y, si aplica, en portugués); 1 = rico sin disputa; no apto => fuera."""
    if wants_pt:
        return 0 if c.e0_pt_cases > 0 else 9  # el dataset no tiene clientes en portugués: solo los casos de estrés de E0
    return 0 if c.e0_cases > 0 else 1


def select_links(
    platform_customers: dict[str, dict[str, str]], candidates: list[Candidate]
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """`platform_customers`: {"CUS-…": {"country": "CO", "locale": "es-CO"}}. Devuelve (vínculos, informe)."""
    used: set[str] = set()
    links: dict[str, str] = {}
    report: list[dict[str, Any]] = []
    eligible = [c for c in candidates if c.active_core_products >= 1 and c.transactions >= MIN_TRANSACTIONS]
    for pid in sorted(platform_customers):  # sorted: el resultado no depende del orden del archivo
        info = platform_customers[pid]
        wants_pt = is_portuguese(info["locale"])
        pool = [c for c in eligible if c.customer_id not in used and _tier(c, wants_pt) < 9]
        if not pool:
            raise LinkError(f"No hay un cliente del dataset elegible para {pid} ({info}); relaje MIN_TRANSACTIONS o amplíe el pool.")
        best = min(pool, key=lambda c: (_tier(c, wants_pt), c.country_iso2 != info["country"], _rank(pid, c.customer_id)))
        used.add(best.customer_id)
        links[pid] = best.customer_id
        report.append({
            "platform_customer": pid,
            "dataset_customer": best.customer_id,
            "wanted": {"country": info["country"], "locale": info["locale"]},
            "dataset_country": best.country_iso2,
            "country_matches": best.country_iso2 == info["country"],
            "language_note": ("el dataset solo tiene español: el portugués viene de los casos de estrés de E0"
                              if wants_pt else "español"),
            "active_core_products": best.active_core_products,
            "transactions": best.transactions,
            "e0_cases": best.e0_cases,
            "e0_pt_cases": best.e0_pt_cases,
            "digital_sessions_90d": best.digital_sessions_90d,
        })
    return links, report


def candidates_from_warehouse(con: duckdb.DuckDBPyConnection) -> list[Candidate]:
    rows = con.execute(
        f"""
        with prod as (
            select customer_id,
                   count(*) filter (where product_status = 'Active' and product_type in {CORE_PRODUCTS}) as active_core
            from gold_restricted.customer_products group by 1),
        tx as (select customer_id, count(*) as n from gold_restricted.customer_transactions group by 1),
        e0 as (
            select customer_id, count(*) as n, count(*) filter (where language = 'pt') as n_pt
            from canonical.cases where source_system = 'e0_sample' group by 1),
        dig as (select customer_id, sessions_90d from gold_restricted.customer_digital_summary)
        select p.customer_id, p.country_iso2,
               coalesce(prod.active_core, 0), coalesce(tx.n, 0), coalesce(e0.n, 0), coalesce(e0.n_pt, 0),
               coalesce(dig.sessions_90d, 0)
        from gold_restricted.customer_profile p
        left join prod using (customer_id) left join tx using (customer_id)
        left join e0 using (customer_id) left join dig using (customer_id)
        where p.customer_status = 'Active'"""
    ).fetchall()
    return [Candidate(*r) for r in rows]


_SEED = re.compile(r'CustomerSeed\(\s*(\d+),\s*"([^"]+)",\s*(\w+),\s*"([^"]+)",\s*(\w+)')
_LOCALES = {"ES_CO": "es-CO", "ES_MX": "es-MX", "ES_AR": "es-AR", "PT_BR": "pt-BR"}


def parse_platform_seed(text: str) -> dict[str, dict[str, str]]:
    """Lee los CustomerSeed de support-platform (`seed/customers.py`): id, país e idioma. Los nombres NO se copian."""
    out: dict[str, dict[str, str]] = {}
    for number, _name, locale, _city, country in _SEED.findall(text):
        out[f"CUS-{int(number):026d}"] = {"country": country, "locale": _LOCALES.get(locale, locale)}
    if not out:
        raise LinkError("No se encontró ningún CustomerSeed en el archivo.")
    return out


def write_outputs(links: dict[str, str], report: list[dict[str, Any]], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "bank-links.json").write_text(json.dumps(links, indent=2, sort_keys=True), encoding="utf-8")
    summary = {
        "links": len(links),
        "country_matches": sum(1 for r in report if r["country_matches"]),
        "with_e0_case": sum(1 for r in report if r["e0_cases"] > 0),
        "portuguese": sum(1 for r in report if r["e0_pt_cases"] > 0),
    }
    (out_dir / "bank-links.report.json").write_text(
        json.dumps({"summary": summary, "links": report}, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description="Genera bank-links.json para la plataforma")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--customers", help="JSON {CUS-…: {country, locale}}")
    g.add_argument("--platform-seed", help="ruta a support-platform/.../seed/customers.py")
    p.add_argument("--out-dir", default=None, help="por defecto <PIPELINE_ROOT>/demo")
    a = p.parse_args()
    settings = Settings.from_env()
    customers = (json.loads(Path(a.customers).read_text(encoding="utf-8")) if a.customers
                 else parse_platform_seed(Path(a.platform_seed).read_text(encoding="utf-8")))
    con = duckdb.connect(settings.warehouse_path, read_only=True)
    links, report = select_links(customers, candidates_from_warehouse(con))
    out_dir = Path(a.out_dir) if a.out_dir else Path(os.environ.get("PIPELINE_ROOT", "data")) / "demo"
    write_outputs(links, report, out_dir)
    print(f"{len(links)} vínculos en {out_dir}")


if __name__ == "__main__":
    main()
