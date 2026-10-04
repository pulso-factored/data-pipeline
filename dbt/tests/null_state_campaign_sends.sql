-- Nulos de ESTADO de campaign_sends: open/click/conversion solo existen si el evento ocurrió; y la apertura solo se
-- mide en Email, Push y SMS entregados. Cualquier violación es un dato incoherente.
select send_id, send_channel, was_delivered, was_opened
from {{ ref('campaign_sends') }}
where (was_opened is true and open_ts is null)
   or (coalesce(was_opened, false) is false and open_ts is not null)
   or (was_clicked and click_ts is null) or (not was_clicked and click_ts is not null)
   or (had_conversion and conversion_ts is null) or (not had_conversion and conversion_ts is not null)
   or (was_clicked and not coalesce(was_opened, false))
   or (had_conversion and not was_clicked)
   or (was_opened is not null and (not was_delivered or send_channel in ('Voice', 'WhatsApp')))
