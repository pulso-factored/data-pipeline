-- Regla 7 (límite por nivel): hasta el límite de su nivel una persona actúa sin aprobación; por encima
-- necesita la de una supervisora. Por eso human_only sin approval_id es válido. Lo que NO es válido:
select 'call_references_missing_approval' as violation, call_id as id
from {{ ref('tool_calls') }}
where approval_id is not null and approval_id not in (select approval_id from {{ ref('approvals') }})
union all
select 'approval_executes_missing_call', approval_id
from {{ ref('approvals') }}
where executed_call_id is not null and executed_call_id not in (select call_id from {{ ref('tool_calls') }})
union all
select 'approved_without_execution', approval_id
from {{ ref('approvals') }}
where decision = 'approved' and executed_call_id is null
