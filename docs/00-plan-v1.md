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

## Modelo canónico (decisión: un solo molde, `source_system`)

E0 no es una fuente aparte con otro esquema: es la muestra del modelo de la plataforma (`platform_history` v0.5.1), construida con datos reales del reto (reclamo, cliente, producto, analista, cargo) más partes generadas (mensajes, herramientas, aprobaciones). Las tres fuentes convergen en ese contrato, en el esquema `canonical`, con `source_system`:

| source_system | Cómo entra |
|---|---|
| `e0_sample` | Casi 1:1 (ya está en formato). `customer_id` se resuelve al cliente real del banco por `complaint_id` (el de E0 es un seudónimo `PSN-`, mapeo 1:1 verificado) |
| `bank_complaints` | Mapeo de `complaints` al contrato (canal/origen, prioridad `critical -> high`, tema solo para las 2 subcategorías de disputa, resolución por texto -> código). Se excluyen los reclamos ya presentes en E0 |
| `cc_platform` | Pendiente: subconjunto del mismo contrato, según el esquema real del `event_log` |

Campos sin fuente quedan NULL (no se inventan): p. ej. `sla_due_at` en los reclamos del banco; `csat` fuera de 1..4 se anula y se conserva en `csat_raw` (el banco usa 1-5). `labels` y `timeline` viven en `bronze_eval/`, fuera del canónico, y un test impide referenciarlos fuera de `dbt/models/eval/`.

## Incremental y calidad

- Modelos incrementales `delete+insert` por `transaction_id` con watermark de ingesta (`_ingested_at`): una partición reingestada por etag nuevo reemplaza sus filas, lo que cubre llegadas tardías y correcciones. `process_date` es la fecha local (UTC-6) y no sirve como watermark.
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
