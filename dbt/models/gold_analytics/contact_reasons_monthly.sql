{# Demanda de contactos del call center por mes, país, canal y motivo: resolución en el primer contacto, escalamiento,
   espera y duración. Evidencia para priorizar el workflow. Sin PII.
   OJO: contact_reason == reason_category (6 valores), no es una taxonomía de intención; y was_resolved mezcla todos los
   tipos de queja, no se puede enlazar a una disputa (complaints.origin_interaction_id está vacío).
   wait_time_seconds solo existe en llamadas entrantes y duration_seconds en llamadas y video: los promedios ignoran los
   nulos estructurales (ver null_policy). #}
select
    cast(date_trunc('month', i.interaction_ts) as date)        as month,
    cu.country_iso2,
    i.channel,
    i.interaction_type,
    i.contact_reason,
    count(*)                                                   as contacts,
    count(*) filter (where i.was_resolved)                     as resolved_contacts,
    count(*) filter (where i.was_escalated)                    as escalated_contacts,
    count(*) filter (where i.requires_followup)                as followup_contacts,
    avg(i.wait_time_seconds)                                   as avg_wait_seconds,
    avg(i.duration_seconds)                                    as avg_duration_seconds,
    avg(i.sentiment_score)                                     as avg_sentiment_score
from {{ ref('interactions') }} i
join {{ ref('customers') }} cu on cu.customer_id = i.customer_id
group by all
