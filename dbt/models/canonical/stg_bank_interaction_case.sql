{{ config(materialized='view') }}
{# Interacciones del call center mapeadas al contrato (case · desde interacciones, COVERAGE.md).
   Lo que no existe en el origen queda NULL: topic (contact_reason solo tiene 6 valores y no es la taxonomía de
   intención), priority, sla_due_at y complaint_id (una llamada no se puede enlazar con su reclamo).
   - channel: Web es video (en el dataset 'Web' solo aparece con interaction_type Video).
   - origin: customer para entrantes; una llamada saliente la inicia el banco y el contrato no tiene ese valor => NULL.
   - language: de la transcripción cuando existe (25%); si no, español supuesto (language_source). #}
select
    i.interaction_id                                          as case_id,
    i.customer_id,
    i.customer_id                                             as source_customer_id,
    i.interaction_ts                                          as opened_at,
    ch.channel,
    case when t.detected_language in ('es', 'pt') then t.detected_language else 'es' end as language,
    case when t.detected_language in ('es', 'pt') then 'source' else 'assumed_es' end    as language_source,
    case when i.interaction_type = 'Outbound Call' then cast(null as varchar) else 'customer' end as origin,
    cast(null as varchar)                                     as topic,
    cast(null as varchar)                                     as complaint_id,
    cast(null as varchar)                                     as priority,
    cast(null as timestamp)                                   as sla_due_at,
    i.agent_id                                                as assigned_analyst_id,
    'bank_interactions'                                       as source_system,
    i._batch_id, i._ingested_at
from {{ ref('interactions') }} i
left join {{ ref('ref_interaction_channel') }} ch on ch.raw_value = i.channel
left join {{ ref('call_transcripts') }} t on t.interaction_id = i.interaction_id
