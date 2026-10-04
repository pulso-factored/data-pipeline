"""Contrato de lectura de los read-models. Warehouse sintético mínimo: no usa datos del reto."""

from __future__ import annotations

import json
import re
from pathlib import Path

import duckdb
import pytest

from pipeline.publish import PublishError, publish
from pipeline.read_contract import CONTRACT_VERSION, DATASET_CUTOFF, ORDER_BY, TABLES, ContractError

ROOT = Path(__file__).resolve().parents[2]


def _warehouse(path: Path, extra_restricted: str = "") -> Path:
    con = duckdb.connect(str(path))
    con.execute("create schema gold_analytics; create schema gold_restricted; create schema gold_masked")
    con.execute("create table gold_analytics.case_facts as select 'CASE-1' as case_id, 'cus_abc' as customer_pseudo")
    con.execute("""create table gold_restricted.customer_products as
        select * from (values ('C2', 'P2', 'credit_card', 500.00, true, false, date '2024-01-01'),
                              ('C1', 'P1', 'savings_account', null, false, false, date '2023-01-01'),
                              ('C1', 'P3', 'credit_card', null, true, true, date '2025-01-01'))
        t(customer_id, product_id, product_type, credit_limit, credit_limit_applicable, is_missing_credit_limit, opening_date)""")
    con.execute("""create table gold_masked.customer_products as
        select * from (values ('cus_b', 'P2', date '2024-01-01'), ('cus_a', 'P1', date '2023-01-01')) t(customer_pseudo, product_id, opening_date)""")
    con.execute("create table gold_restricted.pseudonym_map as select 'C1' as customer_id, 'cus_a' as customer_pseudo")
    con.execute(extra_restricted)
    con.close()
    return path


def _published(tmp_path: Path, **kw) -> tuple[Path, dict]:
    out = publish(_warehouse(tmp_path / "w.duckdb", **kw), tmp_path, "run-c")
    return out, json.loads((out / "read_model_contract.json").read_text(encoding="utf-8"))


def test_contract_describes_grain_subject_nulls_and_flags(tmp_path: Path) -> None:
    _, c = _published(tmp_path)
    assert c["contract_version"] == CONTRACT_VERSION and c["as_of"] == DATASET_CUTOFF
    t = c["zones"]["restricted"]["tables"]["customer_products"]
    assert t["subject_column"] == "customer_id" and t["key"] == ["product_id"]
    limit = t["columns"]["credit_limit"]
    assert limit["class"] == "financial"
    assert limit["null_type"] == "structural"  # heredado de la política de nulos de silver.products
    assert set(limit["related_flags"]) == {"credit_limit_applicable", "is_missing_credit_limit"}
    masked = c["zones"]["masked"]["tables"]["customer_products"]
    assert masked["subject_column"] == "customer_pseudo" and masked["physical_order"].startswith("customer_pseudo")
    assert "class" not in masked["columns"]["product_id"]  # la clasificación solo viaja con la zona restringida
    assert "pseudonym_map" not in c["zones"]["restricted"]["tables"]  # nunca se describe lo que no se publica


def test_published_read_models_are_physically_sorted_by_their_subject(tmp_path: Path) -> None:
    out, _ = _published(tmp_path)
    con = duckdb.connect()
    con.execute(f"attach '{(out / 'gold_restricted.duckdb').as_posix()}' as r (read_only)")
    ids = [x[0] for x in con.execute("select customer_id from r.gold_restricted.customer_products").fetchall()]
    assert ids == sorted(ids)
    con.execute(f"attach '{(out / 'gold_masked.duckdb').as_posix()}' as m (read_only)")
    pseudo = [x[0] for x in con.execute("select customer_pseudo from m.gold_masked.customer_products").fetchall()]
    assert pseudo == sorted(pseudo)


def test_the_contract_is_part_of_the_release_hashes(tmp_path: Path) -> None:
    out, _ = _published(tmp_path)
    release = json.loads((out / "release.json").read_text(encoding="utf-8"))
    assert "read_model_contract.json" in release["artifacts_sha256"]


def test_an_undocumented_read_model_blocks_publication_and_leaves_nothing_behind(tmp_path: Path) -> None:
    wh = _warehouse(tmp_path / "w.duckdb", extra_restricted="create table gold_restricted.customer_loans as select 'C1' as customer_id")
    with pytest.raises((ContractError, PublishError), match="customer_loans"):
        publish(wh, tmp_path, "run-x")
    assert not (tmp_path / "publish" / "run-x").exists()  # el reintento no queda bloqueado por inmutabilidad
    assert not (tmp_path / "publish" / "latest.json").exists()


def test_every_dbt_read_model_has_a_documented_contract() -> None:
    """Anti-deriva: un read-model nuevo en dbt sin grano ni semántica documentados rompe este test."""
    for zone in ("gold_restricted", "gold_masked"):
        for f in (ROOT / "dbt" / "models" / zone).glob("*.sql"):
            name = f.stem.removeprefix("masked_")
            assert name in TABLES and name in ORDER_BY, f"{zone}/{f.name} no tiene contrato documentado"


def test_dataset_cutoff_matches_the_dbt_variable() -> None:
    text = (ROOT / "dbt" / "dbt_project.yml").read_text(encoding="utf-8")
    assert re.search(r'dataset_cutoff:\s*"([0-9-]+)"', text).group(1) == DATASET_CUTOFF
