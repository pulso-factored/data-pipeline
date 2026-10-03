{# Hechos por caso, seudonimizados (cliente = HMAC). SIN columnas de labels. Los conteos son del contacto
   completo (útiles para análisis); NO son entradas válidas para decidir dentro del contacto.
   replay_rank / split se derivan de opened_at (E0): arranque = primeros 200, reproduccion = el resto. #}
with e0_rank as (
    select case_id, row_number() over (order by opened_at, case_id) as replay_rank
    from {{ ref('cases') }}
    where source_system = 'e0_sample'
),
turn_agg as (
    select case_id, count(*) as n_turns, count(*) filter (where author_role = 'customer') as n_customer_turns
    from {{ ref('turns') }} group by 1
),
tool_agg as (
    select case_id, count(*) as n_tool_calls, count(*) filter (where permission_level = 'human_only') as n_human_only_calls
    from {{ ref('tool_calls') }} group by 1
),
appr_agg as (select case_id, count(*) as n_approvals from {{ ref('approvals') }} group by 1),
cq_agg as (select case_id, count(*) as n_copilot_queries from {{ ref('copilot_queries') }} group by 1),
idc_agg as (select case_id, count(*) as n_identity_checks from {{ ref('identity_checks') }} group by 1)
select
    pm.customer_pseudo,
    c.case_id, c.source_system, c.opened_at, c.channel, c.origin, c.topic, c.priority, c.language,
    cu.country_iso2, cu.segment,
    cc.closed_at, cc.resolved, cc.resolution_code, cc.csat,
    coalesce(t.n_turns, 0) as n_turns, coalesce(t.n_customer_turns, 0) as n_customer_turns,
    coalesce(tc.n_tool_calls, 0) as n_tool_calls, coalesce(tc.n_human_only_calls, 0) as n_human_only_calls,
    coalesce(a.n_approvals, 0) as n_approvals, coalesce(q.n_copilot_queries, 0) as n_copilot_queries,
    coalesce(i.n_identity_checks, 0) as n_identity_checks,
    r.replay_rank,
    case when r.replay_rank <= 200 then 'arranque' when r.replay_rank is not null then 'reproduccion' end as split
from {{ ref('cases') }} c
left join {{ ref('customers') }} cu on cu.customer_id = c.customer_id
left join {{ ref('pseudonym_map') }} pm on pm.customer_id = c.customer_id
left join {{ ref('case_closes') }} cc on cc.case_id = c.case_id
left join e0_rank r on r.case_id = c.case_id
left join turn_agg t on t.case_id = c.case_id
left join tool_agg tc on tc.case_id = c.case_id
left join appr_agg a on a.case_id = c.case_id
left join cq_agg q on q.case_id = c.case_id
left join idc_agg i on i.case_id = c.case_id
