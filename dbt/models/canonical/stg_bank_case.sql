{{ config(materialized='view') }}
{# Reclamos del banco mapeados al contrato (reglas verificadas contra lo que E0 hizo con los mismos reclamos).
   - Se excluyen los reclamos que ya tienen un caso en E0 (evita contar dos veces la misma disputa).
   - Campos sin fuente quedan NULL (no se inventan): sla_due_at no existe en complaints.
   - language: el dataset es 100% español; se marca language_source = assumed_es.
   - topic: solo las dos subcategorías de disputa tienen traducción a la taxonomía (36% de llenado). #}
select
    c.complaint_id                                   as case_id,
    c.customer_id,
    c.customer_id                                    as source_customer_id,
    c.creation_date                                  as opened_at,
    ch.channel,
    'es'                                             as language,
    'assumed_es'                                     as language_source,
    ch.origin,
    t.topic,
    c.complaint_id,
    case c.priority when 'critical' then 'high' else c.priority end as priority,
    cast(null as timestamp)                          as sla_due_at,
    c.assigned_agent_id                              as assigned_analyst_id,
    'bank_complaints'                                as source_system,
    c._batch_id, c._ingested_at
from {{ ref('complaints') }} c
left join {{ ref('ref_reception_channel') }} ch on ch.raw_value = c.reception_channel
left join {{ ref('ref_dispute_topic') }} t on t.raw_value = c.subcategory
where c.complaint_id not in (select complaint_id from {{ bronze_e0('case') }})
