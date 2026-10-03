select rate_date, source_currency, target_currency, count(*) as n
from {{ ref('exchange_rates') }}
group by 1, 2, 3
having count(*) > 1
