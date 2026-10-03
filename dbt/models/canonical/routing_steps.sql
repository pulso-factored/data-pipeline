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
