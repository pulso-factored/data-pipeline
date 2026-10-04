{# Tabla canónica `case_close`. E0 pasa tal cual; los reclamos del banco entran solo si tienen fecha de cierre.
   csat: el banco usa 1-5 y el contrato 1-4; fuera de 1..4 queda NULL y el valor original va en csat_raw. #}
select
    case_id, closed_at, closed_by_role, resolved, contact_reason, resolution_code, followup_at,
    cast(csat as integer)                            as csat,
    cast(csat as integer)                            as csat_raw,
    'e0_sample'                                      as source_system
from {{ bronze_e0('case_close') }}

union all by name

select
    c.complaint_id                                   as case_id,
    coalesce(c.closing_date, c.resolution_date)      as closed_at,
    'analyst'                                        as closed_by_role,
    c.status in ('Resolved', 'Closed')               as resolved,
    'Queja'                                          as contact_reason,
    r.resolution_code,
    cast(null as timestamp)                          as followup_at,
    case when c.resolution_satisfaction between 1 and 4 then c.resolution_satisfaction end as csat,
    c.resolution_satisfaction                        as csat_raw,
    'bank_complaints'                                as source_system
from {{ ref('complaints') }} c
left join {{ ref('ref_resolution_code') }} r on r.raw_value = c.resolution
where coalesce(c.closing_date, c.resolution_date) is not null
  and c.complaint_id not in (select complaint_id from {{ bronze_e0('case') }})

union all by name

select
    i.interaction_id                                 as case_id,
    i.interaction_ts + to_seconds(i.duration_seconds) as closed_at,
    'analyst'                                        as closed_by_role,
    i.was_resolved                                   as resolved,
    i.contact_reason,
    cast(null as varchar)                            as resolution_code,
    cast(null as timestamp)                          as followup_at,
    case when s.csat between 1 and 4 then s.csat end as csat,
    s.csat                                           as csat_raw,
    'bank_interactions'                              as source_system
from {{ ref('interactions') }} i
left join (
    select interaction_id, max_by(main_score, survey_ts) as csat
    from {{ ref('satisfaction_surveys') }}
    where survey_type = 'CSAT' and interaction_id is not null
    group by 1
) s on s.interaction_id = i.interaction_id
where i.duration_seconds is not null  -- sin duración no hay hora de cierre (contrato: closed_at obligatorio)
