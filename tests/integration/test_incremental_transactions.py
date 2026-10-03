"""Corrección del update incremental de silver.transactions.

FIXTURE SINTÉTICA: datos inventados, no provienen del dataset del reto. El dataset es estático,
así que la carga incremental se demuestra simulando una segunda entrega con una partición nueva
y una corrección de una partición ya cargada (etag y _ingested_at nuevos).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import duckdb
import pytest

REPO = Path(__file__).resolve().parents[2]
DBT = ["uv", "run", "dbt"]
DBT_ARGS = ["--project-dir", str(REPO / "dbt"), "--profiles-dir", str(REPO / "dbt")]

CUSTOMER_COLS = [
    "customer_id", "document_number", "document_type", "first_name", "last_name", "date_of_birth",
    "gender", "email", "mobile_phone", "landline_phone", "address", "city", "state", "country",
    "postal_code", "detected_accent", "segment", "credit_score", "estimated_monthly_income",
    "occupation", "marital_status", "education_level", "registration_date",
    "registration_branch_id", "customer_status", "last_updated", "accepts_marketing",
]
PRODUCT_COLS = [
    "product_id", "customer_id", "product_type", "product_number", "currency", "current_balance",
    "credit_limit", "interest_rate", "opening_date", "expiration_date", "opening_branch_id",
    "product_status", "opening_channel", "has_linked_app", "days_past_due",
    "last_transaction_date", "last_updated",
]
TX_COLS = [
    "transaction_id", "transaction_date", "process_date", "product_id", "customer_id",
    "transaction_type", "transaction_category", "amount", "currency", "amount_usd", "channel",
    "branch_id", "merchant_name", "merchant_category", "transaction_country", "transaction_city",
    "transaction_status", "response_code", "is_fraud", "fraud_score", "latitude", "longitude",
]
META = ["_batch_id", "_source_file", "_source_etag", "_ingested_at", "_schema_hash"]


def _write(path: Path, cols: list[str], rows: list[dict], ingested_at: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    values = []
    for r in rows:
        full = {c: r.get(c) for c in cols}
        full.update(_batch_id="fx", _source_file=path.name, _source_etag="e", _ingested_at=ingested_at,
                    _schema_hash="h")
        values.append(full)
    sel = " union all ".join(
        "select " + ", ".join(
            (f"timestamp '{v}'" if k == "_ingested_at" else f"'{v}'" if v is not None else "null::varchar")
            + f' as "{k}"' for k, v in row.items()
        )
        for row in values
    )
    con.execute(f"copy ({sel}) to '{path.as_posix()}' (format parquet)")
    con.close()


def _tx(tid: str, ts: str, amount: str, **kw) -> dict:
    base = {
        "transaction_id": tid, "transaction_date": ts, "process_date": ts[:10], "product_id": "P1",
        "customer_id": "C1", "transaction_type": "Purchase", "amount": amount, "currency": "USD",
        "channel": "POS", "transaction_country": "Colombia", "transaction_status": "Approved",
        "is_fraud": "False", "merchant_name": "Tienda", "transaction_category": "Food",
    }
    base.update(kw)
    return base


def _dbt(env: dict, *args: str) -> None:
    res = subprocess.run([*DBT, *args, *DBT_ARGS], cwd=REPO, env=env, capture_output=True, text=True, check=False)
    assert res.returncode == 0, res.stdout[-3000:] + res.stderr[-1000:]


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    bank = tmp_path / "bronze" / "bank"
    t0 = "2026-01-01 00:00:00"
    _write(bank / "customers.parquet", CUSTOMER_COLS, [{
        "customer_id": "C1", "document_number": "D1", "document_type": "DNI", "first_name": "A",
        "last_name": "B", "date_of_birth": "1990-01-01", "country": "Colombia", "city": "Bogota",
        "state": "Cundinamarca", "segment": "Basic", "registration_date": "2023-06-17 00:00:00",
        "registration_branch_id": "BR1", "customer_status": "Active", "accepts_marketing": "true",
        "last_updated": "2024-01-01 00:00:00",
    }], t0)
    _write(bank / "branches.parquet", ["branch_id"], [{"branch_id": "BR1"}], t0)
    _write(bank / "products.parquet", PRODUCT_COLS, [{
        "product_id": "P1", "customer_id": "C1", "product_type": "Cuenta Ahorro", "product_number": "N1",
        "currency": "USD", "current_balance": "10", "opening_date": "2023-06-17", "opening_branch_id": "BR1",
        "product_status": "Active", "opening_channel": "App", "has_linked_app": "true",
        "last_updated": "2024-01-01 00:00:00",
    }], t0)
    _write(bank / "daily_exchange_rates.parquet",
           ["date", "source_currency", "target_currency", "exchange_rate", "buy_rate", "sell_rate", "source"],
           [{"date": "2026-01-01", "source_currency": "COP", "target_currency": "USD",
             "exchange_rate": "0.0002", "buy_rate": "0.0002", "sell_rate": "0.0002", "source": "fixture"}], t0)
    return tmp_path


def test_incremental_picks_up_new_partition_and_corrections(root: Path) -> None:
    env = {**os.environ, "PIPELINE_ROOT": root.as_posix()}
    p1 = root / "bronze" / "bank" / "transactions" / "year=2026" / "month=01" / "day=01" / "t.parquet"
    p2 = root / "bronze" / "bank" / "transactions" / "year=2026" / "month=01" / "day=02" / "t.parquet"

    # Entrega 1: A válida, B válida, C con fecha fuera de rango (cuarentena).
    _write(p1, TX_COLS, [
        _tx("A", "2026-01-01 10:00:00", "100.00"),
        _tx("B", "2026-01-01 11:00:00", "50.00"),
        _tx("C", "2030-01-01 11:00:00", "10.00"),
    ], "2026-01-02 00:00:00")
    _dbt(env, "seed")
    _dbt(env, "run", "-s", "+transactions_checked", "transactions", "q_transactions", "--full-refresh")

    con = duckdb.connect(str(root / "warehouse.duckdb"), read_only=True)
    assert con.execute("select count(*) from silver.transactions").fetchone()[0] == 2
    assert con.execute("select quarantine_reason from quarantine.transactions").fetchall() == [
        ("transaction_date_out_of_range",)
    ]
    con.close()

    # Entrega 2: partición nueva (D, en COP => USD derivado) + corrección de la partición 1
    # (B cambia de monto, C corrige su fecha). _ingested_at posterior = reingesta por etag nuevo.
    _write(p1, TX_COLS, [
        _tx("A", "2026-01-01 10:00:00", "100.00"),
        _tx("B", "2026-01-01 11:00:00", "75.00"),
        _tx("C", "2026-01-01 12:00:00", "10.00"),
    ], "2026-01-03 00:00:00")
    _write(p2, TX_COLS, [_tx("D", "2026-01-01 13:00:00", "1000000.00", currency="COP")],
           "2026-01-03 00:00:00")
    _dbt(env, "run", "-s", "transactions_checked", "transactions", "q_transactions")

    con = duckdb.connect(str(root / "warehouse.duckdb"), read_only=True)
    rows = dict(con.execute("select transaction_id, amount from silver.transactions").fetchall())
    assert sorted(rows) == ["A", "B", "C", "D"]  # sin duplicados, C salió de cuarentena
    assert float(rows["B"]) == 75.0  # la corrección reemplazó la fila
    assert con.execute("select count(*) from quarantine.transactions").fetchone()[0] == 0
    d = con.execute(
        "select amount_usd, amount_usd_source from silver.transactions where transaction_id='D'"
    ).fetchone()
    assert (float(d[0]), d[1]) == (200.0, "derived_fx")  # 1.000.000 COP * 0.0002
    con.close()
