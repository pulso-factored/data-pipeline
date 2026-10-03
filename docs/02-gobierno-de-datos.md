# Gobierno de datos y enmascaramiento

Estado a 2026-10-03. Separa lo que el código **impone hoy** de lo que es **diseño o brecha**. Una convención no es un control.

## Principio de reparto

| Capa | Responsabilidad |
|---|---|
| Este pipeline (ETL) | Entregar dato limpio, **clasificado**, con lineage, y separado físicamente por sensibilidad. Publicar las reglas de enmascaramiento como datos. |
| `agent-core` M7 | **Aplicar** el enmascaramiento y la tokenización en runtime (vistas `full`, `model`, `audit`). No limpia datos. |
| Infra (IAM, KMS, S3) | **Hacer cumplir** quién lee qué artefacto. |

El enforcement de políticas de negocio es de runtime, no de la ETL (docs de agent-core).

## Qué se impone hoy (con prueba)

| Control | Cómo | Dónde se comprueba |
|---|---|---|
| Catálogo de clasificación en el formato de agent-core | Seed `field_classification` -> `field_classification.json` con `field_class`, `tag` y regla `quasi` (`drop` / `age_bucket`). 545 entradas validadas con el `FieldRule` real de agent-core. Campo no resuelto => `pii_direct` | `tests/unit/test_export_catalog.py` |
| Ninguna columna expuesta sin clasificar | Test dbt sobre `information_schema` (silver base, canonical, gold_restricted) | `field_classification_coverage` |
| Sin PII directa en analytics | Test dbt + guardia de publicación (falla cerrado) | `gold_analytics_has_no_direct_pii`, `publish.check_guards` |
| Seudonimización | HMAC-SHA256 con `PSEUDONYM_KEY`, calculado en lote. La clave no pasa por SQL, `target/` ni logs. Mapa de re-identificación en `gold_restricted`, **nunca publicado** | `pseudonym_map.py`, `test_publish.py` |
| Separación física de artefactos | `gold_analytics.duckdb` y `gold_restricted.duckdb` distintos; publicaciones inmutables; `latest.json` se conmuta al final | `test_publish.py` |
| Zona del evaluador | `labels`/`timeline` en `bronze_eval/`; test impide referenciarlos fuera de `dbt/models/eval/`; el publish bloquea campos `final_*` | `test_no_label_leak.py`, `publish.check_guards` |
| Enmascarado para consumidores sin `agent-core` | `gold_masked`: read-models por cliente con PII parcial, **generados desde el mismo catálogo** (macro `masked_select`): nombre `R***`, documento/teléfono `***8972`, email `r***@***`, fecha de nacimiento -> rango de 10 años, casi-identificadores eliminados, texto libre con emails y números limpiados, cliente -> `customer_pseudo`. Columnas enmascaradas con sufijo `_masked` para que la guardia verifique por nombre | `masked_values_do_not_leak`, `test_publish.py`, `scripts/verify_masking.py` |
| Texto libre (`untrusted_text`) identificado | Clase propia en el catálogo (8 columnas) para que M7 lo delimite y tokenice | catálogo |
| Barrido de PII en texto libre | Emails y secuencias de 6+ dígitos en `turns.text`, preguntas/respuestas del copiloto, notas y reclamos. Hoy: 0 hallazgos (aviso, no bloqueo) | `untrusted_text_pii_scan` |
| Sin secretos ni datos en git | Historial revisado: 0 coincidencias de claves/bucket. `data/`, `*.duckdb`, `*.parquet` ignorados. Fixtures sintéticas | auditoría 2026-10-03 |
| Lineage | `_batch_id`, `_source_file`, `_ingested_at` en bronze y silver; `release.json` con git sha, hashes de artefactos y filas por tabla | `publish.py` |
| Nulos explicados | Cada columna con nulos tiene tipo (structural, state, derivable, missing_real, not_in_source); un test falla si hay un nulo sin explicar | `dq_unexplained_nulls` |
| Cuarentena auditable | Filas inválidas salen de silver con motivo; nada se borra de bronze | `dq_quarantine` |

## Reglas de enmascaramiento (viven como datos en el catálogo)

| Clase | Vista `model` (LLM) | Vista `audit` | Ejemplos |
|---|---|---|---|
| `pii_direct` | token estable por run `⟦tag:n⟧` | enmascarado + huella con clave | nombre, documento, email, teléfono, dirección, número de producto, `customer_id` |
| `pii_quasi` | `drop`, salvo `date_of_birth` -> `age_bucket` (rango de 10 años) | igual | fecha de nacimiento, ciudad, código postal, coordenadas, género, ids de analista y sucursal |
| `financial` | pasa | pasa | saldos, montos, score, límite |
| `untrusted_text` | delimitado `<datos_no_confiables>` y con PII tokenizada | enmascarado | descripción/resolución del reclamo, mensajes, respuestas del copiloto |
| `public` | pasa | pasa | estados, canales, fechas de evento |

Decisión consciente: `customer_id` es `pii_direct` (el modelo ve un token, no el identificador).

## Matriz de acceso objetivo (a imponer con IAM en el despliegue)

| Artefacto | Lector previsto | Notas |
|---|---|---|
| `bronze/` | solo el pipeline | copia fiel, incluye PII y texto sin tratar |
| `gold_restricted.duckdb` | tools autenticadas de agent-core | PII en claro y clasificada |
| `gold_masked.duckdb` | consumidores de datos por cliente que no pasan por agent-core | PII parcial e irreversible; enlazable con analytics por `customer_pseudo` |
| `gold_analytics.duckdb` + parquet | análisis, ML, tablero | seudonimizado, sin labels |
| `pseudonym_map` | solo el pipeline | permite re-identificar; no se publica |
| `bronze_eval/` | solo el evaluador | respuestas y resultados posteriores al contacto |
| `PSEUDONYM_KEY` | solo el job de build | Secrets Manager |

## Brechas abiertas (no resueltas, no declarar como cubiertas)

1. **No hay control de acceso real todavía.** DuckDB no tiene roles. La separación de artefactos es física, pero el aislamiento depende de prefijos S3 y políticas IAM que están **por declarar en Terraform** (nada desplegado). Hasta entonces, todo el que lea el disco ve todo.
2. **Gestión de claves:** la clave de seudónimos es una cadena en variable de entorno (local, un archivo ignorado por git). Falta `kid` con rotación, almacén en Secrets Manager/KMS y política de qué pasa con los seudónimos al rotar (hoy cambiarían todos).
3. **Retención y borrado:** sin política. Bronze es inmutable y conserva PII. Falta definir plazos, ciclo de vida S3 y la ruta de borrado por titular. La opción de producción del ADR 0008 (clave por titular con borrado criptográfico) no está implementada.
4. **Auditoría de acceso:** el pipeline registra qué publicó, no quién leyó. Requiere logs de acceso de S3 y CloudTrail de eventos de datos.
5. **PII en texto libre:** el barrido detecta emails y números, **no nombres propios** (mismo límite que el detector de M7). Los datos actuales son plantillas y marcadores; con texto real habría que reevaluar.
6. **Alcance del catálogo:** cubre silver base, canonical y gold_restricted. Faltan las tablas de hechos aún no cargadas (transcripts, encuestas, `digital_events`, `campaign_sends`), que traen texto libre y IP/UTM.
7. **Enmascaramiento propio de la ETL (cubierto parcialmente):** existe `gold_masked`, pero `gold_restricted` sigue en claro y depende de que solo M7 y el pipeline lo lean (ver brecha 1). Las técnicas no son intercambiables: seudonimizar es reversible con la clave (analytics), enmascarar no lo es (masked) y tokenizar en runtime lo hace M7. Si se migra a un motor con políticas de columna (Snowflake, Unity Catalog, Postgres con RLS), las copias se reemplazan por una sola tabla con políticas generadas del mismo catálogo.
7b. **Límites del enmascarado:** `age_bucket`, país, segmento y estado del cliente son cuasi-identificadores que siguen visibles; el riesgo de reidentificación por combinación no se ha medido (no hay k-anonimato calculado).
8. **Términos de uso del reto:** la muestra E0 es "solo para participantes, no publicar". El repo no contiene datos de E0 ni del banco (solo 5 frases genéricas de resolución como seed de mapeo); antes de hacerlo público hay que revisar los seeds contra esos términos.
