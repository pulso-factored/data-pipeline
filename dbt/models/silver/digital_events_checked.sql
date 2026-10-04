{{ config(
    materialized='incremental',
    unique_key='event_id',
    incremental_strategy='delete+insert'
) }}
{# 15,6 M de eventos: incremental por watermark de ingesta (como transactions). customer_id nulo en el 24% de los eventos:
   20% de las sesiones son totalmente anónimas y en otras 498.785 faltan eventos sueltos (derivables, ver digital_sessions).
   ip_address es PII directa; session_id y ubicación son cuasi-identificadores. #}
with src as (
    select *
    from {{ bronze('digital_events', partitioned=true) }}
    {% if is_incremental() %}
    where _ingested_at > (select coalesce(max(_ingested_at), timestamp '1900-01-01') from {{ this }})
    {% endif %}
),
ranked as (
    select *, row_number() over (partition by event_id order by _ingested_at desc) as _rn from src
),
typed as (
    select
        nullif(trim(r.event_id), '')                         as event_id,
        try_cast(r.event_date as timestamp)                  as event_ts,
        cast(try_cast(r.event_date as timestamp) as date)    as event_day,
        try_cast(r.process_date as date)                     as process_date,
        nullif(r.customer_id, '')                            as customer_id,
        r.session_id,
        r.event_type,
        r.event_category,
        r.channel,
        nullif(r.platform, '')                               as platform,
        nullif(r.browser, '')                                as browser,
        nullif(r.app_version, '')                            as app_version,
        nullif(r.page_url, '')                               as page_url,
        nullif(r.page_title, '')                             as page_title,
        nullif(r.action, '')                                 as action,
        nullif(r.element_id, '')                             as element_id,
        nullif(r.product_id, '')                             as product_id,
        try_cast(r.event_value as decimal(15,2))             as event_value,
        try_cast(r.duration_seconds as integer)              as duration_seconds,
        nullif(r.ip_address, '')                             as ip_address,
        nullif(r.ip_country, '')                             as ip_country,
        nullif(r.ip_city, '')                                as ip_city,
        lower(r.is_mobile) = 'true'                          as is_mobile,
        nullif(r.referrer, '')                               as referrer,
        nullif(r.utm_source, '')                             as utm_source,
        nullif(r.utm_medium, '')                             as utm_medium,
        nullif(r.utm_campaign, '')                           as utm_campaign,
        (r.customer_id is null or r.customer_id = '')        as is_anonymous,
        r._batch_id, r._source_file, r._ingested_at, r._rn
    from ranked r
)
select * exclude (_rn),
    case
        when event_id is null then 'null_primary_key'
        when _rn > 1 then 'duplicate_event_id'
        when event_ts is null or event_day not between date '2023-06-17' and date '2026-06-18' then 'event_date_out_of_range'
        when customer_id is not null and customer_id not in (select customer_id from {{ ref('customers') }}) then 'orphan_customer'
        when product_id is not null and product_id not in (select product_id from {{ ref('products_checked') }}) then 'orphan_product'
    end as quarantine_reason
from typed
