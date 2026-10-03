{# `approval`. requester_note es 100% nulo en E0 y decision_note ~77%: notas opcionales. decision_note es untrusted_text. #}
select
    approval_id, case_id, requested_at, requested_by_role, requested_by_id, tool_id,
    cast(params as json) as params,
    reason_code, policy_rule_id,
    cast(requester_note as varchar) as requester_note,
    decided_by, decided_at, decision, decision_note, executed_call_id,
    'e0_sample'                                      as source_system
from {{ bronze_e0('approval') }}
