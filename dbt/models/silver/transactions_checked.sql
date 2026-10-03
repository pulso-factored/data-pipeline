{{ config(
    materialized='incremental',
    unique_key='transaction_id',
    incremental_strategy='delete+insert'
) }}
{# Incremental por watermark de ingesta: una partición reingestada (etag nuevo => _ingested_at nuevo)
   reemplaza sus filas por transaction_id, cubriendo llegadas tardías y correcciones.
   Esta tabla guarda TODAS las filas con su quarantine_reason; silver.transactions y
   quarantine.transactions son vistas sobre ella. #}
with src as (
    select *
    from {{ bronze('transactions', partitioned=true) }}
    {% if is_incremental() %}
    where _ingested_at > (select coalesce(max(_ingested_at), timestamp '1900-01-01') from {{ this }})
    {% endif %}
),
ranked as (
    select *, row_number() over (partition by transaction_id order by _ingested_at desc) as _rn
    from src
),
typed as (
    select
        nullif(trim(t.transaction_id), '')                     as transaction_id,
        try_cast(t.transaction_date as timestamp)              as transaction_ts,
        cast(try_cast(t.transaction_date as timestamp) as date) as event_date,
        try_cast(t.process_date as date)                       as process_date,
        t.product_id,
        t.customer_id,
        lower(t.transaction_type)                              as transaction_type,
        nullif(t.transaction_category, '')                     as transaction_category,
        try_cast(t.amount as decimal(15,2))                    as amount,
        t.currency,
        try_cast(t.amount_usd as decimal(15,2))                as amount_usd_reported,
        lower(t.channel)                                       as channel,
        nullif(t.branch_id, '')                                as branch_id,
        nullif(t.merchant_name, '')                            as merchant_name,
        nullif(t.merchant_category, '')                        as merchant_category,
        c.iso2                                                 as transaction_country_iso2,
        nullif(t.transaction_city, '')                         as transaction_city,
        lower(t.transaction_status)                            as transaction_status,
        nullif(t.response_code, '')                            as response_code,
        lower(t.is_fraud) = 'true'                             as is_fraud,
        try_cast(t.fraud_score as decimal(5,2))                as fraud_score,
        try_cast(t.latitude as decimal(10,7))                  as latitude,
        try_cast(t.longitude as decimal(10,7))                 as longitude,
        t._batch_id, t._source_file, t._ingested_at, t._rn
    from ranked t
    left join {{ ref('ref_country') }} c on c.raw_value = t.transaction_country
),
priced as (
    select
        t.*,
        case
            when t.amount_usd_reported is not null then t.amount_usd_reported
            when t.currency = 'USD' then t.amount
            when fx.exchange_rate is not null then round(t.amount * fx.exchange_rate, 2)  -- aproximación: el reportado difiere ~1% de la tasa del día
        end as amount_usd,
        case
            when t.amount_usd_reported is not null then 'reported'
            when t.currency = 'USD' then 'derived_identity'
            when fx.exchange_rate is not null then 'derived_fx'
            else 'unavailable'
        end as amount_usd_source,
        -- process_date es la fecha local (UTC-6): difiere de event_date en las horas 0-5. NO es llegada tardía.
        (t.process_date is distinct from t.event_date)         as is_partition_date_shifted,
        (t.product_id in (select product_id from {{ ref('products_checked') }} where quarantine_reason is not null)) as product_quarantined,
        (t.fraud_score is null)                                as is_missing_fraud_score,
        (t.merchant_name is null)                              as has_no_merchant
    from typed t
    left join {{ ref('exchange_rates') }} fx
      on fx.rate_date = t.event_date and fx.source_currency = t.currency and fx.target_currency = 'USD'
)
select * exclude (_rn),
    case
        when transaction_id is null then 'null_primary_key'
        when _rn > 1 then 'duplicate_transaction_id'
        when transaction_ts is null
          or event_date not between date '2023-06-17' and date '2026-06-17' then 'transaction_date_out_of_range'
        when amount is null or amount <= 0 then 'non_positive_amount'
        when currency not in ('USD', 'COP', 'ARS') then 'unknown_currency'
        when transaction_country_iso2 is null then 'unknown_country'
        when customer_id not in (select customer_id from {{ ref('customers') }}) then 'orphan_customer'
        when product_id not in (select product_id from {{ ref('products_checked') }}) then 'orphan_product'
    end as quarantine_reason
from priced
