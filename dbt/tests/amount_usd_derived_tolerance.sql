-- Lo derivado por tasa debe quedar cerca de lo reportado (diferencia media observada ~1%). Si se dispara, revisar tasas.
{{ config(severity='warn') }}
select avg(abs(t.amount_usd_reported - round(t.amount * fx.exchange_rate, 2)) / t.amount_usd_reported) as mean_rel_diff
from {{ ref('transactions') }} t
join {{ ref('exchange_rates') }} fx
  on fx.rate_date = t.event_date and fx.source_currency = t.currency and fx.target_currency = 'USD'
where t.amount_usd_reported is not null and t.currency <> 'USD'
having avg(abs(t.amount_usd_reported - round(t.amount * fx.exchange_rate, 2)) / t.amount_usd_reported) > 0.02
