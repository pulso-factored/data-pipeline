{# Embudo digital por día, canal y tipo de evento. Incluye las sesiones anónimas (sirven para demanda y embudo);
   nunca llegan por cliente. Sin PII: sin customer_id ni IP. El cliente de un evento es el reportado o el derivado de su
   sesión (customer_id_resolved). #}
select
    event_day,
    channel,
    event_category,
    event_type,
    count(*)                                                   as events,
    count(distinct session_id)                                 as sessions,
    count(*) filter (where customer_id_resolved is null)       as anonymous_events,
    count(*) filter (where customer_id_source = 'derived_from_session') as events_with_derived_customer,
    count(distinct customer_id_resolved)                       as identified_customers,
    sum(event_value)                                           as event_value,
    avg(duration_seconds)                                      as avg_duration_seconds
from {{ ref('digital_events') }}
group by all
