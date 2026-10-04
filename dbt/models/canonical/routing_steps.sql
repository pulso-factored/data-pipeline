{# `routing_step`. En E0 todo parte de una persona (tier = human); component_id, reason_code, policy_rule_id,
   confidence y handoff son 100% nulos por diseño de la etapa E0 (nulo estructural, no faltante). #}
select
    step_id, case_id, event_time, tier,
    cast(component_id as varchar) as component_id,
    cast(component_version as varchar) as component_version,
    outcome,
    cast(reason_code as varchar) as reason_code,
    cast(policy_rule_id as varchar) as policy_rule_id,
    cast(confidence as double) as confidence,
    from_json(inputs_used, '["VARCHAR"]')            as inputs_used,
    cast(handoff as json) as handoff,
    'e0_sample'                                      as source_system
from {{ bronze_e0('routing_step') }}

union all by name

select
    i.interaction_id                                 as step_id,
    i.interaction_id                                 as case_id,
    i.interaction_ts                                 as event_time,
    'human'                                          as tier,
    cast(null as varchar)                            as component_id,
    cast(null as varchar)                            as component_version,
    -- Aproximación documentada (COVERAGE.md): was_escalated = la analista lo pasó a una supervisora; no se sabe
    -- por qué ni qué hizo después. Un contacto no resuelto ni escalado se registra como mitigated.
    case when i.was_escalated then 'handed_off' when i.was_resolved then 'resolved' else 'mitigated' end as outcome,
    cast(null as varchar)                            as reason_code,
    cast(null as varchar)                            as policy_rule_id,
    cast(null as double)                             as confidence,
    cast(null as varchar[])                          as inputs_used,
    cast(null as json)                               as handoff,
    'bank_interactions'                              as source_system
from {{ ref('interactions') }} i
