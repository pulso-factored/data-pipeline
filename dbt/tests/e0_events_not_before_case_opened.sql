-- Ningún evento de un caso puede ocurrir antes de su apertura.
select 'turn' as entity, t.turn_id as id from {{ ref('turns') }} t join {{ ref('cases') }} c using (case_id) where t.event_time < c.opened_at
union all
select 'tool_call', t.call_id from {{ ref('tool_calls') }} t join {{ ref('cases') }} c using (case_id) where t.event_time < c.opened_at
union all
select 'copilot_query', t.query_id from {{ ref('copilot_queries') }} t join {{ ref('cases') }} c using (case_id) where t.event_time < c.opened_at
