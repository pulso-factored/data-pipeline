"""El dataset del reto y el lago tienen credenciales y regiones distintas; no pueden mezclarse."""

from __future__ import annotations

from pipeline.config import Settings
from pipeline.ingest_bank import dataset_credentials, secret_statements


def _settings() -> Settings:
    return Settings(
        root="s3://lake", dataset_bucket="reto-bucket", dataset_prefix="data/", region="us-east-1",
        dataset_region="us-east-2", work_dir="/work",
    )


def test_dataset_credentials_come_only_from_dataset_variables() -> None:
    env = {"AWS_ACCESS_KEY_ID": "lake-key", "AWS_SECRET_ACCESS_KEY": "lake-secret"}
    assert dataset_credentials(env) is None  # las del entorno estándar NO se toman como del dataset
    env |= {"DATASET_AWS_ACCESS_KEY_ID": "ds-key", "DATASET_AWS_SECRET_ACCESS_KEY": "ds-secret"}
    assert dataset_credentials(env) == ("ds-key", "ds-secret")
    assert dataset_credentials({"DATASET_AWS_ACCESS_KEY_ID": "solo-la-mitad"}) is None


def test_explicit_dataset_credentials_are_scoped_to_the_dataset_bucket_and_region() -> None:
    lake, dataset = secret_statements(_settings(), ("ds-key", "ds-secret"))
    assert "ds-key" not in lake and "ds-secret" not in lake  # el lago nunca ve las claves del reto
    assert "credential_chain" in lake and "'us-east-1'" in lake
    assert "SCOPE 's3://reto-bucket/'" in dataset and "'us-east-2'" in dataset
    assert "KEY_ID 'ds-key'" in dataset


def test_without_dataset_variables_the_dataset_still_uses_the_chain_but_in_its_region() -> None:
    _, dataset = secret_statements(_settings(), None)
    assert "credential_chain" in dataset and "'us-east-2'" in dataset and "SCOPE 's3://reto-bucket/'" in dataset


def test_quotes_in_credentials_cannot_break_out_of_the_statement() -> None:
    _, dataset = secret_statements(_settings(), ("k'ey", "se'cret"))
    assert "KEY_ID 'k''ey'" in dataset and "SECRET 'se''cret'" in dataset


def test_a_local_lake_needs_no_chain_secret() -> None:
    local = Settings(root="data", dataset_bucket="reto-bucket", dataset_prefix="data/", region="us-east-1",
                     dataset_region="us-east-2", work_dir="data")
    statements = secret_statements(local, ("ds-key", "ds-secret"))
    assert len(statements) == 1 and "SECRET dataset" in statements[0]
