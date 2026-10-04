# Contrato de lectura de los read-models y vínculo con la plataforma

Para quien lee los datos del pipeline: el `tool-service` de agent-core (ADR 0004 de support-platform) y la plataforma. Cubre qué se publica y cómo se descubre, cómo leerlo bien, qué significa cada NULL y cómo se vincula un cliente de la plataforma con uno del dataset. Estado a 2026-10-04.

## 1. Qué se publica y cómo se descubre

Cada corrida deja una publicación **inmutable** `publish/<run_id>/` y mueve al final `publish/latest.json`:

| Archivo | Contenido | Quién lo lee |
|---|---|---|
| `gold_restricted.duckdb` | 5 read-models con PII en claro (zona `gold_restricted`) | el tool-service |
| `gold_masked.duckdb` | los mismos read-models con PII parcial; el cliente es `customer_pseudo` | consumidores que no pasan por agent-core |
| `gold_analytics.duckdb` + `parquet/` | agregados seudonimizados | análisis |
| `field_classification.json` | catálogo `FieldClassification` en el formato de agent-core | agent-core (`--field-classifier`) |
| **`read_model_contract.json`** | **contrato de lectura** (ver 2) | tool-service, plataforma, tests de contrato |
| `release.json` | `run_id`, git sha, filas por tabla, hashes, cuarentena | auditoría |

Procedimiento de lectura: leer `latest.json` → `run_id`; abrir `gold_restricted.duckdb` en solo lectura; conservar el `run_id` y devolverlo con cada respuesta (el `dataset_run_id` de ADR 0004 §7). Si el puntero o el archivo no se pueden leer, es un error (`data_unavailable`), nunca un dato viejo en silencio. El puntero solo se mueve cuando la publicación completa terminó, así que no hay estados a medias.

## 2. `read_model_contract.json`

Se genera con cada publicación desde el esquema **real**, el catálogo de clasificación y la política de nulos (no se escribe a mano, así no se desactualiza). Por zona y tabla trae: `grain`, `key`, `subject_column` (`customer_id`, o `customer_pseudo` en la zona enmascarada), `physical_order`, `semantics` (qué significa cada particularidad) y por columna su `type`, `class` (solo en la zona restringida), `null_type` + `null_note` y `related_flags`.

- **Se publica con guardia.** Un read-model nuevo sin grano ni semántica documentados (`pipeline.read_contract`) **bloquea la publicación** antes de crear nada, y un test de deriva lo detecta en CI.
- **Tipos de nulo** (`null_types` del archivo): `structural` no aplica a esa fila; `state` aún no ocurrió; `derivable` se calcula (mira `*_source`); `missing_real` se desconoce, **nunca imputar**; `not_in_source` el origen no lo trae.
- **`as_of` = 2026-06-18**: fin de los datos. "Reciente" se mide contra esa fecha, no contra el reloj; con el reloj real, "últimos 90 días" daría vacío. Un test exige que coincida con la variable `dataset_cutoff` de dbt.

## 3. Cómo leer

1. **Siempre parametrizado por el sujeto**: `WHERE <subject_column> = ?`. El sujeto sale del principal verificado, nunca de un argumento del modelo.
2. **Siempre un `ORDER BY` explícito.** Las tablas se publican ordenadas físicamente por sujeto (`physical_order`) porque acelera la consulta puntual, pero **no es una garantía** de orden de lectura.
3. **Medido** (laptop, DuckDB solo lectura, 150 clientes al azar, transacciones recientes + productos): mediana **19 ms**, p95 **27 ms**, máx. 42 ms. Sin el orden físico eran 57 / 97 / 426 ms. No se midió en la infraestructura real ni bajo carga concurrente.
4. Devolver la fila cruda: la clasificación viaja con el dato (`field_classification.json`), y quien decide qué ve el modelo es el `FieldClassifier` de agent-core. Campo sin clasificar => `pii_direct`.

## 4. Read-models y tools propuestas (ADR 0004 §4)

| Tool | Read-model | Grano | Qué hay que saber |
|---|---|---|---|
| `leer_productos` | `customer_products` | un producto | `credit_limit` NULL + `credit_limit_applicable=false` es **no aplica**; con `true` es **desconocido**. Solo USD/COP/ARS (no hay MXN). |
| `leer_movimientos` / `buscar_transacciones` | `customer_transactions` | una transacción válida | `amount_usd` es **aproximado** si `amount_usd_source='derived_fx'` (~1%). `merchant_*` solo en purchase/payment. `product_quarantined=true`: transacción válida de un producto en cuarentena. País US/ES/BR = compra en el extranjero. |
| `leer_pqr_cliente` | `customer_cases` | un caso | `source_system`: `e0_sample`, `bank_complaints` o `bank_interactions` (en estas, `topic`/`priority` son NULL). `complaint_description` es `untrusted_text`. |
| `leer_perfil` | `customer_profile` | un cliente | NULL = desconocido; mira `is_missing_*`. `branch_link_valid=false` en ~99,99%: no unir por sucursal. |
| (nueva) actividad digital | `customer_digital_summary` | un cliente con actividad en 90 días | Un cliente **ausente** no tiene actividad identificada; no es un desconocido. Sin eventos crudos, IP ni URL. |

`radicar_pqr` y `filed_pqrs` **no son del pipeline**: el pipeline no conoce los PQR radicados por la plataforma y una corrida nueva no los toca. La unión con `customer_cases` es del tool-service (ADR 0004 §6), y la reconciliación con el sistema real del banco sigue siendo la brecha de producción que esa ADR ya nombra.

## 5. Vínculo cliente de la plataforma ↔ cliente del dataset

**Qué es y qué no es.** La plataforma inventa sus clientes de ejemplo a propósito (nunca copia registros del dataset), así que no hay vínculo "natural" por nombre. El vínculo es una **asignación de demostración**: cada cliente de la plataforma recibe un cliente del dataset al que el asistente pueda leerle datos. En producción lo reemplaza la autenticación real del cliente (ADR 0004 §8).

**Cómo se genera** (determinista; mismos datos y mismos clientes => mismos vínculos, sin importar el orden):

```bash
uv run python -m pipeline.demo_links --platform-seed ../support-platform/backend/src/cc_platform/infrastructure/seed/customers.py
# o:  --customers clientes.json   con   {"CUS-…": {"country": "CO", "locale": "es-CO"}}
```

Escribe en `data/demo/` (privado, ignorado por git, **nunca al repo**):
- `bank-links.json`: `{"CUS-…": "<customer_id del dataset>"}`, el formato exacto de `CC_BANK_CUSTOMER_LINKS_FILE`.
- `bank-links.report.json`: por vínculo, qué coincide y cuánta data tiene (solo ids y conteos, sin PII).

**Criterios.** El cliente del dataset debe estar `Active`, tener un producto activo (tarjeta o cuenta) y al menos 20 transacciones, para que el asistente tenga qué leer. Se prefiere uno con una **disputa de E0** (para el flujo de "cargo no reconocido"); si no alcanza, cae a uno rico sin disputa antes de fallar. Coincide en país. Para clientes de la plataforma en portugués solo se usan clientes del dataset con un caso `pt` de E0. Nunca se repite un cliente del dataset, y si no hay candidato suficiente **falla** en vez de vincular a uno pobre.

**Resultado actual** (19 clientes de la semilla de la plataforma): 19 con disputa de E0, 18 con el país coincidente, 3 en portugués.

**Limitaciones que el equipo de la plataforma debe conocer**
1. **El dataset no tiene clientes en Brasil ni en portugués.** El cliente brasileño de la semilla (`1008`) queda vinculado a uno de México; el portugués sale solo de los casos de estrés de E0.
2. **Nombre y ciudad no coinciden.** Los de la plataforma son inventados y los del dataset son otros. Si el flujo de verificación de identidad pregunta datos del dataset (ciudad, últimos movimientos), el cliente simulado tiene que responder con los del dataset vinculado, no con los de su ficha en la plataforma.
3. Es una asignación de demostración: no hay endpoint para editarla, y cambia si cambia el dataset o la lista de clientes.

## 6. Visibilidad por rol (punto abierto 1 de la ADR 0004): propuesta, NO decidida

Quién ve qué campo es una política de autorización (`AuthzPort` de agent-core), no del pipeline: el pipeline aporta la clasificación y nada más. Como punto de partida para `leer_perfil`, proponemos:

| Rol | Ve | No ve |
|---|---|---|
| Asistente (agente de IA de cara al cliente) | `customer_id` (token), `first_name` para saludar, `country_iso2`, `segment`, `customer_status` | documento, correo, teléfonos, dirección, fecha de nacimiento, `credit_score`, ingresos |
| Asesor | lo anterior + `document_type` y los últimos 4 del documento y del teléfono | `credit_score` e ingresos salvo en flujos de crédito con política propia |

Requiere decisión de gobierno de datos antes de implementarse.

## 7. Qué falta para producción

- **Frescura:** el tool-service consulta el puntero con un TTL (60 s); una notificación de "nueva corrida" no existe (punto abierto 3 de la ADR).
- **Control de acceso real** a los archivos: depende de los permisos por prefijo de `infra` (`docs/02-gobierno-de-datos.md`, brecha 1). Hoy, quien lea el disco ve todo.
- **Latencia bajo carga y en la infraestructura real:** sin medir.
