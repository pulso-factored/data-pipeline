{# Desempeño de campañas por mes, campaña y canal. Las tasas usan como denominador solo lo que es medible:
   apertura, clic y conversión únicamente en Email/Push/SMS entregados. En Voice y WhatsApp son 0 POR CONSTRUCCIÓN (no se
   rastrean), no porque no ocurran: usar engagement_measurable_delivered como denominador. Sin PII. #}
select
    cast(date_trunc('month', s.send_ts) as date)               as month,
    s.campaign_id,
    c.campaign_name, c.campaign_type, c.campaign_objective,
    s.send_channel,
    count(*)                                                   as sends,
    count(*) filter (where s.was_delivered)                    as delivered,
    count(*) filter (where s.was_opened is not null)           as open_measurable,
    count(*) filter (where s.was_delivered and s.send_channel in ('Email', 'Push', 'SMS')) as engagement_measurable_delivered,
    count(*) filter (where s.was_opened)                       as opened,
    count(*) filter (where s.was_clicked)                      as clicked,
    count(*) filter (where s.had_conversion)                   as conversions,
    sum(s.conversion_value)                                    as conversion_value,
    sum(s.send_cost)                                           as send_cost,
    count(*) filter (where s.is_missing_send_cost)             as sends_without_cost
from {{ ref('campaign_sends') }} s
join {{ ref('marketing_campaigns') }} c on c.campaign_id = s.campaign_id
group by all
