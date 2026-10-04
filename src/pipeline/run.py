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
# ingest_e0 es una carga única y manual (la muestra es restringida): no entra en la corrida programada.
STEPS = ("ingest_bank", "build", "publish")
ALL_STEPS = ("ingest_bank", "ingest_e0", "build", "publish")
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
            Path(settings.work_dir).mkdir(parents=True, exist_ok=True)
            env = {
                **os.environ,
                "WAREHOUSE_PATH": settings.warehouse_path,
                "DBT_TARGET_PATH": f"{settings.work_dir}/target",
                "DBT_LOG_PATH": f"{settings.work_dir}/logs",
                "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
            }
            res = subprocess.run(
                [sys.executable, "-m", "dbt.cli.main", "build", "--project-dir", str(dbt), "--profiles-dir", str(dbt),
                 "--target", "s3" if settings.is_remote else "dev"],
                check=False, env=env,
            )
            if res.returncode != 0:
                raise SystemExit(f"dbt build falló (código {res.returncode}); no se publica.")
        elif step == "publish":
            print(f"publicado en {publish.publish_from_settings(settings)}")


def main() -> None:
    p = argparse.ArgumentParser(description="Runner del pipeline de datos")
    p.add_argument("--steps", default=",".join(STEPS))
    p.add_argument("--bank-tables", default=",".join(ingest_bank.ALL_TABLES))
    a = p.parse_args()
    steps = tuple(s.strip() for s in a.steps.split(",") if s.strip())
    unknown = set(steps) - set(ALL_STEPS)
    if unknown:
        raise SystemExit(f"Pasos desconocidos: {sorted(unknown)}; válidos: {ALL_STEPS}")
    run(steps, tuple(t.strip() for t in a.bank_tables.split(",") if t.strip()))


if __name__ == "__main__":
    main()
