"""Runner del pipeline: ingest -> build -> publish. Es el único entrypoint del contenedor (ECS).

    python -m pipeline.run                      # todo
    python -m pipeline.run --steps build,publish

Falla pronto si falta algo del entorno, sin imprimir valores de secretos.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from pipeline import ingest_bank, ingest_e0, publish
from pipeline.config import Settings

REPO = Path(__file__).resolve().parents[2]
STEPS = ("ingest_bank", "ingest_e0", "build", "publish")
REQUIRED = {
    "ingest_bank": ("PIPELINE_ROOT", "DATASET_BUCKET"),
    "ingest_e0": ("PIPELINE_ROOT", "E0_SOURCE_DIR"),
    "build": ("PIPELINE_ROOT", "PSEUDONYM_KEY"),
    "publish": ("PIPELINE_ROOT",),
}


def check_env(steps: tuple[str, ...]) -> None:
    missing = sorted({v for s in steps for v in REQUIRED[s] if not os.environ.get(v)})
    if missing:
        raise SystemExit(f"Faltan variables de entorno: {', '.join(missing)}")


def run(steps: tuple[str, ...], bank_tables: tuple[str, ...] = ingest_bank.ALL_TABLES) -> None:
    check_env(steps)
    settings = Settings.from_env()
    for step in steps:
        print(f"== {step}", flush=True)
        if step == "ingest_bank":
            ingest_bank.run(bank_tables)
        elif step == "ingest_e0":
            ingest_e0.run(Path(os.environ["E0_SOURCE_DIR"]))
        elif step == "build":
            dbt = REPO / "dbt"
            res = subprocess.run(
                [sys.executable, "-m", "dbt.cli.main", "build", "--project-dir", str(dbt), "--profiles-dir", str(dbt)],
                check=False,
            )
            if res.returncode != 0:
                raise SystemExit(f"dbt build falló (código {res.returncode}); no se publica.")
        elif step == "publish":
            out = publish.publish(Path(settings.root) / "warehouse.duckdb", Path(settings.root))
            print(f"publicado en {out}")


def main() -> None:
    p = argparse.ArgumentParser(description="Runner del pipeline de datos")
    p.add_argument("--steps", default=",".join(STEPS))
    p.add_argument("--bank-tables", default=",".join(ingest_bank.ALL_TABLES))
    a = p.parse_args()
    steps = tuple(s.strip() for s in a.steps.split(",") if s.strip())
    unknown = set(steps) - set(STEPS)
    if unknown:
        raise SystemExit(f"Pasos desconocidos: {sorted(unknown)}; válidos: {STEPS}")
    run(steps, tuple(t.strip() for t in a.bank_tables.split(",") if t.strip()))


if __name__ == "__main__":
    main()
