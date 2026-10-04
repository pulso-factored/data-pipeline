"""Guardias de publicación. Warehouse sintético mínimo: no usa datos del reto."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from pipeline.publish import PublishError, publish


def _warehouse(path: Path, *, analytics_extra: str = "", restricted_extra: str = "", masked_extra: str = "") -> Path:
    con = duckdb.connect(str(path))
    con.execute("create schema gold_analytics; create schema gold_restricted; create schema gold_masked")
    con.execute(f"create table gold_analytics.case_facts as select 'CASE-1' as case_id, 'cus_abc' as customer_pseudo {analytics_extra}")
    con.execute("create table gold_analytics.dq_quarantine as select 'products' as table_name, 'duplicate_product_number' as outcome, 6 as rows")
    con.execute(f"create table gold_restricted.customer_profile as select 'CLI-1' as customer_id, 'Ana' as first_name {restricted_extra}")
    con.execute(f"create table gold_masked.customer_profile as select 'cus_abc' as customer_pseudo, 'A***' as first_name_masked {masked_extra}")
    con.execute("create table gold_restricted.pseudonym_map as select 'CLI-1' as customer_id, 'cus_abc' as customer_pseudo")
    con.close()
    return path


def test_publish_separates_artifacts_and_never_ships_the_reidentification_map(tmp_path: Path) -> None:
    wh = _warehouse(tmp_path / "warehouse.duckdb")
    out = publish(wh, tmp_path, "run-test")

    assert {p.name for p in out.iterdir()} >= {
        "gold_analytics.duckdb", "gold_restricted.duckdb", "gold_masked.duckdb", "field_classification.json",
        "release.json", "parquet"}
    restricted = duckdb.connect(str(out / "gold_restricted.duckdb"), read_only=True)
    tables = {r[0] for r in restricted.execute("select table_name from information_schema.tables where table_schema='gold_restricted'").fetchall()}
    assert tables == {"customer_profile"}  # pseudonym_map NO se publica
    analytics = duckdb.connect(str(out / "gold_analytics.duckdb"), read_only=True)
    assert "customer_profile" not in {r[0] for r in analytics.execute("select table_name from information_schema.tables").fetchall()}

    release = json.loads((out / "release.json").read_text(encoding="utf-8"))
    assert release["run_id"] == "run-test"
    assert "pseudonym_map" in release["never_published"]
    assert release["quarantine"] == [{"table": "products", "reason": "duplicate_product_number", "rows": 6}]
    assert release["artifacts_sha256"]["gold_analytics.duckdb"]
    assert json.loads((tmp_path / "publish" / "latest.json").read_text(encoding="utf-8"))["run_id"] == "run-test"


def test_guard_blocks_direct_pii_in_analytics(tmp_path: Path) -> None:
    wh = _warehouse(tmp_path / "w.duckdb", analytics_extra=", 'ana@x.com' as email")
    with pytest.raises(PublishError, match="PII directa"):
        publish(wh, tmp_path, "r1")
    assert not (tmp_path / "publish" / "latest.json").exists()  # no hubo conmutación


def test_guard_blocks_unclassified_restricted_columns(tmp_path: Path) -> None:
    wh = _warehouse(tmp_path / "w.duckdb", restricted_extra=", 1 as brand_new_column")
    with pytest.raises(PublishError, match="sin clasificar"):
        publish(wh, tmp_path, "r1")


def test_guard_blocks_evaluator_fields(tmp_path: Path) -> None:
    wh = _warehouse(tmp_path / "w.duckdb", analytics_extra=", 'resolved' as final_status")
    with pytest.raises(PublishError, match="evaluador"):
        publish(wh, tmp_path, "r1")


def test_publications_are_immutable(tmp_path: Path) -> None:
    wh = _warehouse(tmp_path / "w.duckdb")
    publish(wh, tmp_path, "same")
    with pytest.raises(PublishError, match="inmutables"):
        publish(wh, tmp_path, "same")


def test_masked_artifact_is_published_and_guarded(tmp_path: Path) -> None:
    out = publish(_warehouse(tmp_path / "ok.duckdb"), tmp_path, "run-masked")
    masked = duckdb.connect(str(out / "gold_masked.duckdb"), read_only=True)
    cols = {r[0] for r in masked.execute("select column_name from information_schema.columns where table_schema='gold_masked'").fetchall()}
    assert cols == {"customer_pseudo", "first_name_masked"}

    leaky = _warehouse(tmp_path / "leaky.duckdb", masked_extra=", 'ana@x.com' as email")
    with pytest.raises(PublishError, match="gold_masked.customer_profile contiene PII directa"):
        publish(leaky, tmp_path, "run-leaky")


def _eval_db(path: Path, extra_schema: bool = False) -> Path:
    """Se construye con otro nombre y se copia a `path`: en producción el archivo se llama eval.duckdb, igual que su
    esquema, y la publicación tiene que calificar el catálogo para no confundirlos."""
    import shutil

    build = path.with_name("build.duckdb")
    con = duckdb.connect(str(build))
    con.execute("create schema eval")
    con.execute("create table eval.labels as select 'CASE-1' as case_id, 'Resolved' as final_status")
    if extra_schema:
        con.execute("create schema silver; create table silver.customers as select 'CLI-1' as customer_id")
    con.close()
    shutil.copy(build, path)
    return path


def test_eval_zone_is_published_outside_publish_and_keeps_its_answers(tmp_path: Path) -> None:
    from pipeline.publish import publish_eval

    out = publish_eval(_eval_db(tmp_path / "eval.duckdb"), tmp_path, "eval-1")
    assert out == tmp_path / "bronze_eval" / "eval" / "eval-1"
    assert not (tmp_path / "publish").exists()  # nunca bajo publish/: lo leerían los consumidores
    con = duckdb.connect()
    con.execute(f"attach '{(out / 'eval.duckdb').as_posix()}' as ev (read_only)")
    assert con.execute("select final_status from ev.eval.labels").fetchone() == ("Resolved",)
    release = json.loads((out / "release.json").read_text(encoding="utf-8"))
    assert release["zone"] == "evaluator-only"
    latest = json.loads((tmp_path / "bronze_eval" / "eval" / "latest.json").read_text(encoding="utf-8"))
    assert latest["run_id"] == "eval-1"


def test_eval_database_must_contain_only_the_eval_schema(tmp_path: Path) -> None:
    from pipeline.publish import publish_eval

    with pytest.raises(PublishError, match="solo el esquema eval"):
        publish_eval(_eval_db(tmp_path / "bad.duckdb", extra_schema=True), tmp_path, "eval-bad")
