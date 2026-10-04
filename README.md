# data-pipeline

Pipeline analítico (arquitectura medallón: bronze, silver, gold) con dbt + DuckDB para el sistema de atención bancaria de Pulso. Entrega datos limpios, con contrato y trazables a `agent-core` y a análisis/ML. No cubre lo transaccional.

- Plan: [docs/00-plan-v1.md](docs/00-plan-v1.md)
- Gobierno de datos y enmascaramiento: [docs/02-gobierno-de-datos.md](docs/02-gobierno-de-datos.md)
- Hallazgos de calidad del dataset: [docs/01-hallazgos-de-calidad.md](docs/01-hallazgos-de-calidad.md)

## Reglas

- Nunca credenciales ni datos reales en el repo. Las credenciales del bucket del reto van por variables de entorno.
- `labels` de la muestra E0 es solo para el evaluador.

Estado: rebanada 9 lista: las 13 tablas del dataset ya están en silver (campañas y eventos digitales incluidos) (silver, modelo canónico `platform_history`, gold_restricted y gold_analytics, catálogo FieldClassification y marts de calidad). 195 comprobaciones de dbt + 24 tests.

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

## Credenciales y regiones (dataset del reto vs. lago)

El bucket del reto está en otra cuenta y otra región que el lago. Se usan credenciales y regiones separadas:

| Variable | Para qué |
|---|---|
| `DATASET_BUCKET`, `DATASET_PREFIX`, `DATASET_REGION` (def. `us-east-2`) | dónde está el dataset |
| `DATASET_AWS_ACCESS_KEY_ID`, `DATASET_AWS_SECRET_ACCESS_KEY` | credenciales de solo lectura del reto; solo valen para ese bucket |
| `AWS_DEFAULT_REGION` (def. `us-east-1`) y la cadena estándar de AWS (rol de la tarea) | el lago |

No use `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` para las claves del reto en producción: tienen prioridad sobre el rol de la tarea y el pipeline escribiría en el lago con claves de otra cuenta. Sin `DATASET_AWS_*` (desarrollo local) el dataset usa la cadena estándar.

## Zona del evaluador

`labels` y `timeline` (las respuestas) nunca entran al warehouse ni a `publish/`. Se construyen aparte, a demanda:

```bash
python -m pipeline.run --steps ingest_e0,build,eval   # requiere E0_SOURCE_DIR; escribe bronze_eval/eval/<run>/eval.duckdb
```

El paso `eval` usa el target `eval` (o `eval_s3`) de dbt con `--vars "{build_eval: true}"`: su base es `EVAL_PATH` y el warehouse se adjunta en solo lectura únicamente para las comprobaciones cruzadas. En S3 queda bajo `bronze_eval/eval/`, protegido por el módulo `data_lake` de infra (solo el evaluador lee).

## Rendimiento

Un build completo (232 comprobaciones, 15,6 M de eventos digitales y 4,4 M de transacciones) tarda ~6 min en una laptop. Los perfiles usan **1 hilo de dbt** (`DBT_THREADS`): DuckDB ya paraleliza cada consulta, y con 4 hilos los modelos competían por los mismos núcleos y la memoria. Medido, el mismo modelo tardó 10 s aislado y 417 s dentro de un build de 4 hilos (`customer_transactions`). CPU y memoria en Fargate siguen sin medirse.
