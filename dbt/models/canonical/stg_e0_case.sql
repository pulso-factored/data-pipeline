{{ config(materialized='view') }}
{# Casos de la muestra E0, ya en el formato del contrato platform_history.
   customer_id canónico = cliente REAL del banco, resuelto por complaint_id (el de E0 es un seudónimo PSN-).
   El seudónimo se conserva en source_customer_id. #}
select
    e.case_id,
    s.customer_id                      as customer_id,
    e.customer_id                      as source_customer_id,
    e.opened_at,
    e.channel,
    e.language,
    'source'                           as language_source,
    e.origin,
    e.topic,
    e.complaint_id,
    e.priority,
    e.sla_due_at,
    e.assigned_analyst_id,
    'e0_sample'                        as source_system,
    e._batch_id, e._ingested_at
from {{ bronze_e0('case') }} e
left join {{ ref('complaints') }} s on s.complaint_id = e.complaint_id
