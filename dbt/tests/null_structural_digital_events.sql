-- Nulos estructurales de digital_events: duration solo en PageView, event_value solo en FormSubmit/Purchase,
-- browser solo en web y app_version solo en apps. Fuera de lo aplicable no debe venir informado.
select event_id, event_type, channel
from {{ ref('digital_events') }}
where (event_type <> 'PageView' and duration_seconds is not null)
   or (event_type not in ('FormSubmit', 'Purchase') and event_value is not null)
   or (channel in ('Android App', 'iOS App') and browser is not null)
   or (channel in ('Desktop Web', 'Mobile Web') and app_version is not null)
