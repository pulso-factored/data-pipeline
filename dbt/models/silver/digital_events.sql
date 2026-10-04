{{ config(materialized='view') }}
{# customer_id_resolved: el reportado, o el cliente único de su sesión cuando el evento no lo trae. customer_id_source
   dice cuál (reported | derived_from_session | anonymous). Los marts por cliente usan customer_id_resolved. #}
select
    e.* exclude (quarantine_reason),
    coalesce(e.customer_id, s.session_customer_id)                   as customer_id_resolved,
    case when e.customer_id is not null then 'reported'
         when s.session_customer_id is not null then 'derived_from_session'
         else 'anonymous' end                                        as customer_id_source
from {{ ref('digital_events_checked') }} e
left join {{ ref('digital_sessions') }} s on s.session_id = e.session_id
where e.quarantine_reason is null
