# data-pipeline

Pipeline analítico (arquitectura medallón: bronze, silver, gold) con dbt + DuckDB para el sistema de atención bancaria de Pulso. Entrega datos limpios, con contrato y trazables a `agent-core` y a análisis/ML. No cubre lo transaccional.

- Plan: [docs/00-plan-v1.md](docs/00-plan-v1.md)
- Hallazgos de calidad del dataset: [docs/01-hallazgos-de-calidad.md](docs/01-hallazgos-de-calidad.md)

## Reglas

- Nunca credenciales ni datos reales en el repo. Las credenciales del bucket del reto van por variables de entorno.
- `labels` de la muestra E0 es solo para el evaluador.

Estado: rebanada 4 lista (silver, modelo canónico `platform_history`, gold_restricted y gold_analytics, catálogo FieldClassification y marts de calidad). 144 comprobaciones de dbt + 7 tests.

## Uso local

```bash
uv sync
export PIPELINE_ROOT=/ruta/absoluta/data PSEUDONYM_KEY=$(python -c "import secrets;print(secrets.token_hex(32))") DATASET_BUCKET=... AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=...
uv run python -m pipeline.ingest_bank --tables customers,products,complaints
uv run python -m pipeline.ingest_e0 --source /ruta/a/pulso_muestra_e0   # snapshot E0; labels van a bronze_eval/
uv run dbt build --project-dir dbt --profiles-dir dbt
uv run pytest
```
