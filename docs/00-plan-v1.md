# Plan v1: pipeline de datos analítico (dbt + DuckDB, arquitectura medallón)

Estado: borrador para iterar. Entrega del proyecto: 2026-10-05.

## Objetivo

Entregar datos limpios, con contrato y trazables para `agent-core` (read-models por cliente y catálogo `FieldClassification`, ver su ADR 0008) y para análisis/ML. No es lo transaccional.

## Fuentes

| Fuente | Dev | Producción |
|---|---|---|
| Dataset del banco (S3 del reto, 13 tablas, ~5,3 GB CSV, hechos particionados por día) | `read_csv` de DuckDB con `httpfs` | Igual, desde tarea ECS; credenciales en Secrets Manager |
| Muestra E0 (11 parquets, 2.000 casos de disputas) | Local | Se carga una vez a S3 y se versiona. Join con el banco por `complaint_id` |
| `event_log` de la Plataforma CC | Export a archivo o SQLite | Rol de BD de solo lectura, watermark por `sequence` |
| Eventos de `agent-core` (outbox SNS/SQS) | Fixtures sintéticos | Consumidor con dedup por `event_id` (fase posterior) |

`data_backup_20260831/` se descarta (ver hallazgos).

## Capas

- **Bronze:** copia fiel en parquet, solo se agrega. Metadatos: `_batch_id`, `_source_file`, `_etag`, `_ingested_at`, `_schema_hash`. Manifiesto de archivos para detectar particiones nuevas o cambiadas.
- **Silver:** tipado, dedup por PK, normalización por seeds (países ISO, enums canónicos), política de nulos por campo, cuarentena (`quarantine_<tabla>` con motivo), modelo canónico de caso (`complaints` + E0 + Plataforma CC) alineado con `platform_history` v0.5.1. Contratos dbt (`contract: enforced`) y tests.
- **Gold:**
  - `gold_restricted`: read-models por cliente con PII en claro y clasificada, solo para tools autenticadas de agent-core.
  - `gold_analytics`: seudonimizado (HMAC con clave en secretos) para análisis y ML: demanda y motivos, calidad y frescura, splits `arranque`/`reproduccion` sin fuga.
  - `labels` de E0 en esquema aparte, solo para el evaluador.
  - Catálogo `FieldClassification` (seed): `pii_direct`, `pii_quasi`, `financial`, `untrusted_text`, `public`. Campo sin clasificar = `pii_direct`.

## Incremental y calidad

- Modelos incrementales por `process_date` con ventana de lookback calibrada con la diferencia observada entre `process_date` y la fecha del evento.
- Para datos estáticos, una fixture etiquetada demuestra la corrección del update (lo pide el reto).
- Tests que fallan si aparecen duplicados o evolución de esquema (hoy no existen).
- Mart de calidad y frescura: % de cuarentena, nulos por tipo, frescura por fuente.

## Orquestación y despliegue

- Runner Python propio (`ingest -> dbt build -> publish`), una imagen, lanzada por EventBridge Scheduler como tarea ECS (módulo `scheduled_task` de `infra`).
- Artefactos en S3 con KMS: `gold.duckdb` de solo lectura, parquet por tabla y `release.json` (run_id, hashes, frescura) como puntero atómico.
- Cuarto workload de `infra` con su ADR. Se declara y valida con Terraform, sin afirmar que esté desplegado. Brechas esperadas para `OPEN_GAPS.md`: egress hacia el bucket del reto (otra cuenta, `us-east-2`), secretos y rol de BD de solo lectura de la Plataforma CC.

## Reglas duras

- Nunca credenciales (AWS del diccionario, claves HMAC) en el repo, en `profiles.yml` versionado ni en requests a modelos.
- Sin datos reales en fixtures públicos: solo sintéticos.
- `labels` jamás entra a silver ni a gold analítico por cliente. Los campos `final_*` son fuga dentro del contacto.
- El enforcement de políticas es de runtime; la ETL entrega el dato limpio.

## Orden de trabajo

1. Esqueleto, bronze y silver de `customers`, `products`, `complaints`, `transactions` y E0.
2. Gold, tests de calidad e incremental.
3. Docker, Terraform, ADR y documentación.
