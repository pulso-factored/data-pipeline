# data-pipeline

Pipeline analítico (arquitectura medallón: bronze, silver, gold) con dbt + DuckDB para el sistema de atención bancaria de Pulso. Entrega datos limpios, con contrato y trazables a `agent-core` y a análisis/ML. No cubre lo transaccional.

- Plan: [docs/00-plan-v1.md](docs/00-plan-v1.md)
- Hallazgos de calidad del dataset: [docs/01-hallazgos-de-calidad.md](docs/01-hallazgos-de-calidad.md)

## Reglas

- Nunca credenciales ni datos reales en el repo. Las credenciales del bucket del reto van por variables de entorno.
- `labels` de la muestra E0 es solo para el evaluador.

Estado: rebanada 1 lista (bronze incremental por etag; silver y cuarentena de customers, products, complaints).

## Uso local

```bash
uv sync
export PIPELINE_ROOT=/ruta/absoluta/data DATASET_BUCKET=... AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=...
uv run python -m pipeline.ingest_bank --tables customers,products,complaints
uv run dbt build --project-dir dbt --profiles-dir dbt
uv run pytest
```
