from pipeline.ingest_bank import needs_ingest, relative_output, schema_hash, table_of

PREFIX = "data/"


def test_relative_output_dimension():
    assert relative_output("data/customers.csv", PREFIX) == "customers.parquet"


def test_relative_output_fact_partition():
    key = "data/complaints/year=2024/month=03/day=05/complaints_20240305.csv"
    assert relative_output(key, PREFIX) == "complaints/year=2024/month=03/day=05/complaints_20240305.parquet"


def test_table_of():
    assert table_of("data/customers.csv", PREFIX) == "customers"
    assert table_of("data/transactions/year=2023/month=06/day=17/t.csv", PREFIX) == "transactions"


def test_needs_ingest_new_changed_unchanged():
    obj = {"key": "k", "etag": "e2"}
    assert needs_ingest(obj, {}) == "new"
    assert needs_ingest(obj, {"k": "e1"}) == "changed"  # llegada tardía / corrección
    assert needs_ingest(obj, {"k": "e2"}) is None


def test_schema_hash_is_order_sensitive_and_stable():
    assert schema_hash(["a", "b"]) == schema_hash(["a", "b"])
    assert schema_hash(["a", "b"]) != schema_hash(["b", "a"])
    assert schema_hash(["a", "b"]) != schema_hash(["a", "b", "c"])  # evolución de esquema
