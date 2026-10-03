{# `identity_check`: registra qué preguntas se hicieron y el resultado, nunca las respuestas. #}
select
    check_id, case_id, started_at, ended_at, actor_role, actor_id, channel_session,
    from_json(questions, '["VARCHAR"]')              as questions,
    questions_version, cast(correct as integer) as correct, result,
    cast(attempt as integer) as attempt, policy_rule_id, trigger,
    'e0_sample'                                      as source_system
from {{ bronze_e0('identity_check') }}
