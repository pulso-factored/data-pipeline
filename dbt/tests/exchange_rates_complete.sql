-- 12 pares (4 monedas) por cada día del rango: 1.097 días contiguos.
select count(*) as pairs, count(distinct rate_date) as days
from {{ ref('exchange_rates') }}
having count(*) <> 12 * count(distinct rate_date)
    or count(distinct rate_date) <> date_diff('day', min(rate_date), max(rate_date)) + 1
