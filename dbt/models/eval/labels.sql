{# Respuestas del evaluador: lo que el componente debe acertar (objetivo), lo que hizo la persona (referencia) y lo que
   ocurrió días después del contacto (final_*, posterior: usarlo dentro del contacto es una fuga).
   Nunca se lee fuera de esta zona. #}
select
    case_id,
    cast(rank as integer)                         as rank,
    split,
    try_cast(opened_at as timestamp)              as opened_at,
    subcategory,
    language,
    hard_case,
    expected_behavior,
    stress_test,
    charge_found,
    cast(amount_usd as decimal(15,2))             as amount_usd,
    from_json(expected_actions, '["VARCHAR"]')    as expected_actions,
    expected_identity_check,
    needs_person,
    from_json(needs_person_reasons, '["VARCHAR"]') as needs_person_reasons,
    analyst_style,
    customer_behaviors,
    human_actions,
    human_errors,
    final_status,
    final_resolution_code,
    try_cast(final_resolution_date as timestamp)  as final_resolution_date,
    final_sla_breached,
    _batch_id, _contract_version, _ingested_at
from {{ bronze_eval('labels') }}
