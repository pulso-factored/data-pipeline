# data-pipeline

Pipeline analítico (arquitectura medallón: bronze, silver, gold) con dbt + DuckDB para el sistema de atención bancaria de Pulso. Entrega datos limpios, con contrato y trazables a `agent-core` y a análisis/ML. No cubre lo transaccional.

- Plan: [docs/00-plan-v1.md](docs/00-plan-v1.md)
- Gobierno de datos y enmascaramiento: [docs/02-gobierno-de-datos.md](docs/02-gobierno-de-datos.md)
- Hallazgos de calidad del dataset: [docs/01-hallazgos-de-calidad.md](docs/01-hallazgos-de-calidad.md)

## Reglas

- Nunca credenciales ni datos reales en el repo. Las credenciales del bucket del reto van por variables de entorno.
- `labels` de la muestra E0 es solo para el evaluador.

Estado: rebanada 5 lista (+ gold_masked, publicación con guardias y runner) (silver, modelo canónico `platform_history`, gold_restricted y gold_analytics, catálogo FieldClassification y marts de calidad). 161 comprobaciones de dbt + 15 tests.

## Uso local

```bash
uv sync
export PIPELINE_ROOT=/ruta/absoluta/data PSEUDONYM_KEY=$(python -c "import secrets;print(secrets.token_hex(32))") DATASET_BUCKET=... AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=...
uv run python -m pipeline.ingest_bank --tables customers,products,complaints
uv run python -m pipeline.ingest_e0 --source /ruta/a/pulso_muestra_e0   # snapshot E0; labels van a bronze_eval/
uv run dbt build --project-dir dbt --profiles-dir dbt
uv run python -m pipeline.publish   # artefactos separados + release.json (o todo junto: python -m pipeline.run)
uv run pytest
```

## Contenedor

```bash
docker build -t pulso-data-pipeline .
# Corrida programada (ingest_bank, build, publish). ingest_e0 es una carga única y manual.
docker run --rm -e PIPELINE_ROOT=s3://<bucket>/<prefijo> -e DATASET_BUCKET=... -e PSEUDONYM_KEY=... pulso-data-pipeline
```

- Usuario no root (uid 10001), sin red en tiempo de ejecución para DuckDB (la extensión `httpfs` se instala en la imagen).
- `PIPELINE_ROOT` puede ser una ruta local o `s3://`. `WORK_DIR` (por defecto `/work`) es el scratch donde vive `warehouse.duckdb`.
- Con el lake en S3 el runner usa el target `s3` de dbt (credenciales por el rol de la tarea) y sube la publicación con `latest.json` al final.
