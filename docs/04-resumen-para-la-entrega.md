# Ingeniería de datos: resumen para la entrega

Cifras medidas sobre el dataset del reto el 2026-10-04. Todo lo que aquí figura como "no está" también es parte del resumen.

## En una frase

Un pipeline reproducible (dbt + DuckDB, arquitectura medallón) que convierte las 13 tablas del dataset y la muestra E0 en datos limpios, clasificados y trazables para el agente, separados físicamente por sensibilidad, con 232 comprobaciones automáticas y un build completo de ~6 minutos.

## Arquitectura

```
S3 del reto (13 tablas, CSV por día)  ──┐
Muestra E0 (11 parquets)              ──┼─►  BRONZE  copia fiel + lineage (_batch_id, _source_file, _etag, _ingested_at)
Plataforma CC (event_log)  [pendiente] ─┘        │  incremental por etag (partición nueva o cambiada)
                                                 ▼
                                      SILVER   tipado, dedup, normalización, política de nulos, CUARENTENA con motivo
                                          │    modelo canónico = contrato platform_history con source_system
                                          ▼
                    GOLD  ┬─ gold_restricted   PII en claro, clasificada  ─► read-models por cliente (agent-core)
                          ├─ gold_masked       PII parcial, generada del mismo catálogo
                          ├─ gold_analytics    seudonimizada (HMAC), sin labels  ─► demanda, calidad, campañas
                          └─ eval.duckdb       labels/timeline, aislada (solo el evaluador)
```

## Volumen real frente al documentado

| Tabla | Documentado | Real (silver) | A cuarentena |
|---|---:|---:|---:|
| customers | 150.000 | 150.000 | 0 |
| products | 400.000 | 399.994 | 6 |
| transactions | 5.000.000 | 4.423.656 | 1.352 |
| call_center_interactions | 800.000 | 686.121 | 175 |
| call_transcripts | 200.000 | 171.277 | 44 |
| satisfaction_surveys | 250.000 | 212.709 | 50 |
| digital_events | 10.000.000 | **15.620.994** | 0 |
| complaints | 80.000 | 67.095 | 0 |
| campaign_sends | 2.000.000 | 1.746.801 | 0 |
| daily_exchange_rates | 3.000 | 13.164 | 0 |

El diccionario promete ~2% de duplicados, ~5% de nulos, llegadas tardías y evolución de esquema. Medido: **0 duplicados por clave ni por clave de negocio** y **0 evolución de esquema** en las particiones muestreadas; los nulos sí están, y son de cuatro tipos distintos (abajo). Los tests fallan si aparecen duplicados o un esquema nuevo, en lugar de suponer que no.

## Lo que el diccionario no decía

- `data_backup_20260831/` no es un snapshot previo: solo ~4.000 de 150.000 IDs de cliente coinciden. Se descartó.
- `process_date` difiere de la fecha del evento en ~25% de las transacciones y eventos: es un desplazamiento de huso (UTC-6) en las horas 0-5, **no llegadas tardías** (error propio de interpretación que corregimos con datos).
- `transactions.amount_usd` falta en el 100% de las filas en USD y ~5% de COP/ARS. Es derivable, pero el valor reportado difiere ~1% de monto × tasa; se marca `reported | derived_identity | derived_fx`.
- Las llaves de sucursal en `customers` y `service_agents` están rotas (≈99,99% sin enlace). Se marcan, no se usan.
- 13 `employee_code` compartidos por agentes distintos (el diccionario los declara únicos): afectan a ~15.800 interacciones. Se marcan; no se descartan.
- Escalas distintas: CSAT 1-4 (doc 1-5), NPS 2-7 (doc 0-10). No hay moneda MXN en los datos.
- `digital_events`: el 24% sin `customer_id`, pero **no son todas sesiones anónimas**: 20% de las sesiones son totalmente anónimas y otras 498.785 son mixtas, con 624.439 eventos derivables del único cliente de su sesión. (Habíamos afirmado lo contrario antes de medirlo; un test lo desmintió.)
- Transcripciones: 42 plantillas con marcadores `{…}` sin rellenar y una única intención detectada (`consulta_general`). Se conservaron pero no se convierten en `turn` del contrato (no traen hora por mensaje).
- En WhatsApp y Voice los clics y conversiones valen 0 **por construcción** (no se rastrean). Las tasas de campaña usan solo Email, Push y SMS entregados.

## Cómo se maneja

- **Cuatro tipos de nulo, no uno:** estructural (no aplica), de estado (aún no ocurrió), derivable (se calcula, con su origen) y faltante real (nunca se imputa); más "no está en el origen". 104 reglas por columna; un test falla si aparece un nulo sin explicar.
- **Cuarentena con motivo**, nunca borrado: la fila sale de silver, queda en `quarantine.*` y cuenta en el mart de calidad.
- **Contratos:** dbt con contrato enforzado en las dimensiones, validación de E0 contra `platform_history` v0.5.1 (falla si el esquema se rompe), y un contrato de lectura publicado con cada corrida.
- **Reproducible:** todo se regenera desde S3 con un comando; no hay estado manual. Imagen de contenedor verificada sin red.
- **Incremental:** bronze por etag; transacciones y eventos digitales con watermark de ingesta. Como el dataset es estático, la corrección del update se demuestra con una fixture sintética etiquetada (partición nueva + corrección + salida de cuarentena).

## Gobierno y privacidad

- **Catálogo `FieldClassification`** de 506 columnas (41 `pii_direct`, 48 `pii_quasi`, 27 `financial`, 14 `untrusted_text`) en el formato de agent-core, validado con su `FieldRule` real. Un campo sin clasificar se trata como PII directa.
- **Tres zonas de gold + una del evaluador**, publicadas como archivos distintos con guardias que fallan cerrado (sin PII directa fuera de la zona restringida, sin campos del evaluador, sin el mapa de re-identificación).
- **Zona del evaluador:** `labels` y `timeline` en su propia base. El `split` arranque/reproducción se reconstruye desde `opened_at` **sin leer las respuestas**, y un test lo verifica contra `labels` (2.000 de 2.000).
- **Enmascarado generado del catálogo**, no escrito a mano; verificado contra el valor crudo (sin fugas).
- Sin secretos ni datos en el repositorio (historial revisado); credenciales solo por entorno.

## Evidencia de demanda (para elegir el flujo)

- Las dos subcategorías de disputa (**Cargo no reconocido** y **Cobro indebido**) son 24.491 de 67.095 reclamos (36,5%).
- En el call center, la resolución en el primer contacto depende del motivo: **91,5% en Transaccional frente a 43,6% en Queja**, mientras el escalamiento es ~10% en todos. El CSAT medio también es el menor en Queja (2,44 frente a 2,91 en Transaccional).
- Limitación: `contact_reason` solo tiene 6 valores y `was_resolved` no se puede enlazar a una disputa concreta (`origin_interaction_id` está 100% vacío).

## Para el agente

Read-models por cliente (perfil, productos, transacciones, casos, resumen digital) con su contrato de lectura. Consulta puntual por cliente: mediana 19 ms, p95 27 ms (medido en una laptop, sin carga). Detalle en `docs/03-contrato-de-lectura-y-vinculo.md`.

## Lo que NO está (honestidad)

- **No hay nada desplegado.** El Terraform (lago, roles, tarea batch) está declarado y probado solo con proveedor simulado; no se ha corrido `plan` ni `apply`, y el CI de la organización no ha podido ejecutarse (bloqueo de facturación de GitHub Actions).
- **El `tool-service` y el `HttpToolExecutor` de agent-core no existen todavía:** los agentes aún no leen estos datos.
- **E0 es en parte generada** (mensajes, herramientas, aprobaciones); el portugués solo existe en sus casos de estrés. El dataset no tiene clientes en Brasil.
- **La fuente de la Plataforma CC** no está cargada (falta su esquema real).
- Sin medir: CPU y memoria en Fargate, latencia bajo carga, k-anonimato de los cuasi-identificadores.
- El control de acceso real a los archivos depende de permisos de `infra` aún no aplicados: hoy quien lea el disco ve todo.
- Antes de hacer público el repositorio hay que revisar los seeds contra los términos de uso del reto.
