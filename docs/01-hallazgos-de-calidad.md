# Hallazgos de calidad del dataset del reto (perfilado 2026-10-03)

Método: DuckDB leyendo el bucket del reto en solo lectura (sin descargar a disco). Dimensiones completas; hechos completos salvo `digital_events` (muestra de 1 de cada 40 archivos). Reproducible con los scripts de perfilado que pasarán a `scripts/profiling/`.

## Volumen real vs. documentado

| Tabla | Real | Documentado |
|---|---|---|
| transactions | 4.425.008 | 5.000.000 |
| call_center_interactions | 686.296 | 800.000 |
| call_transcripts | 171.321 | 200.000 |
| satisfaction_surveys | 212.759 | 250.000 |
| complaints | 67.095 | 80.000 |
| campaign_sends | 1.746.801 | 2.000.000 |
| daily_exchange_rates | 13.164 | 3.000 |

Los tests de conteo usan los valores reales como línea base.

## Lo que está limpio

- 0 filas con PK duplicada y 0 duplicados por clave de negocio, en las 13 tablas. El "~2% de duplicados" no aparece en `data/`. Los tests deben fallar si aparecen, no suponerlos.
- 0 huérfanos de FK en los hechos (clientes, productos, agentes, sucursales, interacciones).
- Esquema idéntico en todas las particiones muestreadas (sin evolución observada).
- Sin `credit_score` fuera de 300-850, sin fechas de nacimiento inválidas, sin emails inválidos, sin montos <= 0.

## Hallazgos que cambian el diseño

1. **`data_backup_20260831/` no es un snapshot previo de las mismas entidades.** Los IDs coinciden en ~4.000 de 150.000 clientes. Se descarta como fuente.
2. **FK de sucursal rotas en dimensiones:** `customers.registration_branch_id` 149.995/150.000 huérfanos; `service_agents.assigned_branch_id` 831 huérfanos de ~832 no nulos. `products`, `transactions` y `complaints` sí enlazan.
3. **Vocabularios distintos al diccionario** (`Cuenta Ahorro` vs `Savings Account`, `Pasaporte` vs `Passport`, `Web` vs `Web Chat`, `México` vs `Mexico`). Se normaliza con seeds.
4. **No hay MXN** en `products` ni `transactions` (solo USD, COP, ARS).
5. **`transactions.amount_usd`:** nulo en el 100% de las filas en USD y ~5% de COP/ARS. Es derivable.
6. **`process_date` != fecha de `transaction_date` en ~1,1M filas (25%)** y 1.352 fechas fuera de rango o inválidas. Es la señal de llegadas tardías.
7. **Escalas de encuestas:** CSAT 1-4, NPS 2-7, CES 1-4 (el diccionario dice 1-5 y 0-10).
8. **`complaints`:** `origin_interaction_id` 100% vacío; 772 casos Resolved/Closed sin `resolution_date`; `contact_reason` == `reason_category`.
9. 6 `product_number` duplicados; transacciones en USA, Spain y Brazil (~40K cada una).

## Nulos por tipo (política aprobada)

| Tipo | Ejemplos | Tratamiento |
|---|---|---|
| Estructural (no aplica) | `products.credit_limit`/`days_past_due` 69%, `transactions.merchant_*` 77%, `digital_events.product_id` 91% | NULL; test de que sea NULL solo cuando el tipo no aplica |
| De estado (aún no ocurrió) | `complaints.resolution*` 77%, `campaign_sends.click_*`/`conversion_*` 94-99% | NULL + bandera derivada (`is_open`, etc.) |
| Derivable | `transactions.amount_usd`, `call_center_interactions.duration_seconds` | Se calcula con trazabilidad (`*_source = reported \| derived`) |
| Faltante real | `customers.estimated_monthly_income` 20%, `credit_score` 15%, `detected_accent` 30%, `fraud_score` 20% | NULL + `is_missing_*`. Nunca se imputa |

Otros: `digital_events.customer_id` 24% nulo (sesiones anónimas): se mantienen en silver y se excluyen de los read-models por cliente. Filas huérfanas o fuera de dominio: cuarentena con motivo y % en el mart de calidad; nada se borra de bronze.
