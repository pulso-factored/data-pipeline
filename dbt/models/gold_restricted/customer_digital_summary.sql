{# Resumen digital por cliente en los 90 días previos al corte del dataset. NO expone eventos crudos, ni IP, ni URL:
   solo agregados útiles para el agente (actividad reciente, errores, canales). Una fila por cliente con actividad.
   Usa customer_id_resolved: incluye los eventos cuyo cliente se deriva de su sesión. #}
select
    customer_id_resolved                                       as customer_id,
    max(event_ts)                                              as last_event_at,
    max(event_ts) filter (where event_type = 'Login')          as last_login_at,
    count(distinct session_id)                                 as sessions_90d,
    count(*) filter (where event_type = 'Login')               as logins_90d,
    count(*) filter (where event_type = 'Error')               as error_events_90d,
    count(*) filter (where event_type = 'Purchase')            as purchases_90d,
    count(distinct channel)                                    as channels_used_90d,
    max_by(channel, event_ts)                                  as last_channel,
    max_by(app_version, event_ts) filter (where app_version is not null) as last_app_version
from {{ ref('digital_events') }}
where customer_id_resolved is not null
  and event_ts >= timestamp '{{ var("dataset_cutoff") }}' - interval 90 day
group by customer_id_resolved
