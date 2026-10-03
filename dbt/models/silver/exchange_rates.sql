{# 12 pares x 1.097 días (el diccionario dice 3.000 filas; la realidad es 13.164). PK (rate_date, source, target). #}
select
    try_cast(date as date)               as rate_date,
    source_currency,
    target_currency,
    try_cast(exchange_rate as decimal(12,6)) as exchange_rate,
    try_cast(buy_rate as decimal(12,6))  as buy_rate,
    try_cast(sell_rate as decimal(12,6)) as sell_rate,
    source                               as rate_source,
    _batch_id, _source_file, _ingested_at
from {{ bronze('daily_exchange_rates') }}
where try_cast(date as date) is not null
  and try_cast(exchange_rate as decimal(12,6)) > 0
