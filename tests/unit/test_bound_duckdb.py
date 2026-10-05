import duckdb

from pipeline.config import bound_duckdb


def _setting(con, name):
    return con.execute(f"select current_setting('{name}')").fetchone()[0]


def test_sin_variables_no_cambia_nada(monkeypatch):
    monkeypatch.delenv("DUCKDB_MEMORY_LIMIT", raising=False)
    monkeypatch.delenv("DUCKDB_TEMP_DIRECTORY", raising=False)
    plain = _setting(duckdb.connect(), "memory_limit")
    assert _setting(bound_duckdb(duckdb.connect()), "memory_limit") == plain


def test_aplica_limite_y_directorio_temporal(monkeypatch, tmp_path):
    monkeypatch.setenv("DUCKDB_MEMORY_LIMIT", "1500MB")
    monkeypatch.setenv("DUCKDB_TEMP_DIRECTORY", str(tmp_path / "spill"))
    con = bound_duckdb(duckdb.connect())
    assert _setting(con, "memory_limit").startswith("1.3")  # 1500MB = 1.3 GiB
    assert _setting(con, "temp_directory").replace("\\", "/").endswith("/spill")
