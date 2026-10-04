{{ config(materialized='table') }}
{# Envíos de campañas. Tres estados lógicos de apertura: true / false / NULL (no medible: Voice y WhatsApp no rastrean
   aperturas, y un envío no entregado no puede abrirse). open_*, click_* y conversion_* son nulos de ESTADO. #}
with ranked as (
    select *, row_number() over (partition by send_id order by _ingested_at desc) as _rn
    from {{ bronze('campaign_sends', partitioned=true) }}
),
typed as (
    select
        nullif(trim(r.send_id), '')                          as send_id,
        try_cast(r.send_date as timestamp)                   as send_ts,
        cast(try_cast(r.send_date as timestamp) as date)     as event_date,
        try_cast(r.process_date as date)                     as process_date,
        r.campaign_id,
        r.customer_id,
        r.send_channel,
        nullif(r.template_used, '')                          as template_used,
        nullif(r.subject, '')                                as subject,
        r.send_status,
        lower(r.was_delivered) = 'true'                      as was_delivered,
        case lower(r.was_opened) when 'true' then true when 'false' then false end as was_opened,
        try_cast(r.open_date as timestamp)                   as open_ts,
        lower(r.was_clicked) = 'true'                        as was_clicked,
        try_cast(r.click_date as timestamp)                  as click_ts,
        try_cast(r.click_count as integer)                   as click_count,
        lower(r.had_conversion) = 'true'                     as had_conversion,
        try_cast(r.conversion_date as timestamp)             as conversion_ts,
        try_cast(r.conversion_value as decimal(15,2))        as conversion_value,
        nullif(r.open_device, '')                            as open_device,
        nullif(r.open_country, '')                           as open_country,
        nullif(r.failure_reason, '')                         as failure_reason,
        try_cast(r.send_cost as decimal(10,4))               as send_cost,
        (r.send_cost is null or r.send_cost = '')            as is_missing_send_cost,
        r._batch_id, r._source_file, r._ingested_at, r._rn
    from ranked r
)
select * exclude (_rn),
    case
        when send_id is null then 'null_primary_key'
        when _rn > 1 then 'duplicate_send_id'
        when send_ts is null or event_date not between date '2023-06-17' and date '2026-06-18' then 'send_date_out_of_range'
        when customer_id not in (select customer_id from {{ ref('customers') }}) then 'orphan_customer'
        when campaign_id not in (select campaign_id from {{ ref('marketing_campaigns') }}) then 'orphan_campaign'
    end as quarantine_reason
from typed
