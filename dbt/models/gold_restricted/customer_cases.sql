{# Casos por cliente con su estado en el reclamo original y su cierre. `complaint_description` es
   untrusted_text: puede traer instrucciones inyectadas, así que nunca se pasa al modelo sin delimitar. #}
select
    c.case_id, c.customer_id, c.source_system, c.opened_at, c.channel, c.origin, c.topic, c.priority,
    c.assigned_analyst_id,
    k.status                                                as complaint_status,
    k.is_open, k.sla_breached, k.is_repeat_complainer, k.claimed_amount, k.currency as claimed_currency,
    k.description                                           as complaint_description,
    cc.closed_at, cc.resolved, cc.resolution_code, cc.csat
from {{ ref('cases') }} c
left join {{ ref('complaints') }} k on k.complaint_id = c.complaint_id
left join {{ ref('case_closes') }} cc on cc.case_id = c.case_id
