{# `signal`: oportunidades que la plataforma publica para el equipo de agentes. Se calculan con el arranque. #}
select
    signal_id, kind,
    cast(scope as json) as scope,
    window_start, window_end,
    cast(support_cases as integer) as support_cases,
    cast(support_analysts as integer) as support_analysts,
    consistency,
    from_json(evidence_case_ids, '["VARCHAR"]')      as evidence_case_ids,
    status,
    'e0_sample'                                      as source_system
from {{ bronze_e0('signal') }}
