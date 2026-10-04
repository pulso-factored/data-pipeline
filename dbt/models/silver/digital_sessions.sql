{# Una fila por sesión. Una sesión nunca tiene más de un cliente (0 observadas con dos), así que el cliente de una sesión
   mixta (eventos con y sin customer_id: 498.785 sesiones, 624.439 eventos) se puede derivar con seguridad. Las 367.044
   sesiones totalmente anónimas (3,1 M de eventos) no tienen cliente. Esta tabla evita recalcular la ventana por sesión
   en cada modelo que lee digital_events. #}
select
    session_id,
    count(*)                                              as n_events,
    count(distinct customer_id)                           as n_distinct_customers,
    count(*) filter (where customer_id is null)           as n_events_without_customer,
    case when count(distinct customer_id) = 1 then min(customer_id) end as session_customer_id,
    min(event_ts)                                         as first_event_at,
    max(event_ts)                                         as last_event_at
from {{ ref('digital_events_checked') }}
where quarantine_reason is null
group by session_id
