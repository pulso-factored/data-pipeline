{# Agentes de servicio. Una fila por agent_id (gana el último ingestado). Nombres, correo y teléfono son PII;
   native_accent y country_of_origin son cuasi-identificadores. assigned_branch_id es una FK rota en el origen
   (~831 de ~832 no nulos no enlazan con branches): se marca, no se descarta. #}
with ranked as (
    select *, row_number() over (partition by agent_id order by _ingested_at desc) as _rn
    from {{ bronze('service_agents') }}
)
select
    nullif(trim(r.agent_id), '')                          as agent_id,
    r.employee_code,
    (count(*) over (partition by r.employee_code) > 1)   as employee_code_is_duplicated,
    r.first_name,
    r.last_name,
    r.email,
    nullif(r.phone, '')                                   as phone,
    nullif(r.native_accent, '')                           as native_accent,
    c.iso2                                                as country_of_origin_iso2,
    nullif(r.assigned_branch_id, '')                      as assigned_branch_id,
    (b.branch_id is not null)                             as branch_link_valid,
    r.agent_type,
    r.experience_level,
    r.languages,
    nullif(r.specialty, '')                               as specialty,
    try_cast(r.hire_date as date)                         as hire_date,
    try_cast(r.avg_csat as decimal(3,2))                  as avg_csat,
    try_cast(r.total_monthly_interactions as integer)     as total_monthly_interactions,
    r.agent_status,
    r.work_shift,
    r._batch_id, r._source_file, r._ingested_at
from ranked r
left join {{ ref('ref_country') }} c on c.raw_value = r.country_of_origin
left join {{ bronze('branches') }} b on b.branch_id = r.assigned_branch_id
where r._rn = 1 and nullif(trim(r.agent_id), '') is not null
