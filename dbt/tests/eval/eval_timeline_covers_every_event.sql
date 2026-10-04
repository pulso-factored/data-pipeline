{{ config(enabled=var('build_eval', false)) }}
-- timeline es una vista derivada: su conteo por tipo debe igualar al de las entidades de platform_history.
with expected as (
    select 'turn' as kind, count(*) as n from {{ source('wh', 'turns') }}
    union all select 'tool_call', count(*) from {{ source('wh', 'tool_calls') }}
    union all select 'copilot_query', count(*) from {{ source('wh', 'copilot_queries') }}
    union all select 'identity_check', count(*) from {{ source('wh', 'identity_checks') }}
    union all select 'approval_request', count(*) from {{ source('wh', 'approvals') }}
    union all select 'approval_decision', count(*) from {{ source('wh', 'approvals') }} where decision is not null
),
actual as (select kind, count(*) as n from {{ ref('timeline') }} group by 1)
select e.kind, e.n as expected, coalesce(a.n, 0) as actual
from expected e left join actual a using (kind)
where e.n <> coalesce(a.n, 0)
