{# `tool_call`. params y state_change son JSON. #}
select
    call_id, case_id, event_time, actor_role, actor_id, tool_id, tool_version,
    cast(params as json) as params,
    permission_level, confirmed_by, status, verified,
    cast(state_change as json) as state_change,
    cast(retry_count as integer) as retry_count,
    cast(latency_ms as integer) as latency_ms,
    approval_id,
    'e0_sample'                                      as source_system
from {{ bronze_e0('tool_call') }}
