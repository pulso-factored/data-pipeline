{# Demanda de reclamos por mes, país, canal y subcategoría: evidencia para priorizar el workflow. Sin PII. #}
select
    cast(date_trunc('month', k.creation_date) as date)  as month,
    cu.country_iso2,
    k.reception_channel,
    k.category,
    k.subcategory,
    k.priority,
    count(*)                                            as cases,
    count(*) filter (where k.is_open)                   as open_cases,
    count(*) filter (where k.sla_breached)              as sla_breached_cases,
    count(*) filter (where k.is_repeat_complainer)      as repeat_complainer_cases,
    avg(k.resolution_days)                              as avg_resolution_days
from {{ ref('complaints') }} k
join {{ ref('customers') }} cu on cu.customer_id = k.customer_id
group by all
