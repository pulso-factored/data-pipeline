{{ config(materialized='table') }}
{# table, no view: silver, cuarentena y los marts de calidad la leen; una vista la recalcularía en cada uno #}
{# call_center_interactions tipado. contact_reason == reason_category (6 valores): no distingue intenciones.
   Una fila por interaction_id; fuera de rango, huérfanas o con duraciones negativas van a cuarentena. #}
with ranked as (
    select *, row_number() over (partition by interaction_id order by _ingested_at desc) as _rn
    from {{ bronze('call_center_interactions', partitioned=true) }}
),
typed as (
    select
        nullif(trim(r.interaction_id), '')                    as interaction_id,
        try_cast(r.interaction_date as timestamp)             as interaction_ts,
        cast(try_cast(r.interaction_date as timestamp) as date) as event_date,
        try_cast(r.process_date as date)                      as process_date,
        r.customer_id,
        nullif(r.agent_id, '')                                as agent_id,
        r.interaction_type,
        r.channel,
        r.contact_reason,
        r.reason_category,
        try_cast(r.duration_seconds as integer)               as duration_seconds,
        try_cast(r.wait_time_seconds as integer)              as wait_time_seconds,
        lower(r.was_resolved) = 'true'                        as was_resolved,
        lower(r.requires_followup) = 'true'                   as requires_followup,
        nullif(r.detected_sentiment, '')                      as detected_sentiment,
        try_cast(r.sentiment_score as decimal(3,2))           as sentiment_score,
        nullif(r.customer_detected_accent, '')                as customer_detected_accent,
        nullif(r.agent_used_accent, '')                       as agent_used_accent,
        lower(r.was_escalated) = 'true'                       as was_escalated,
        nullif(r.mentioned_products, '')                      as mentioned_products,
        lower(r.has_transcript) = 'true'                      as has_transcript,
        lower(r.has_recording) = 'true'                       as has_recording,
        (r.duration_seconds is null or r.duration_seconds = '')   as is_missing_duration,
        (r.wait_time_seconds is null or r.wait_time_seconds = '') as is_missing_wait_time,
        (try_cast(r.interaction_date as timestamp) is not null
           and cast(try_cast(r.interaction_date as timestamp) as date) is distinct from try_cast(r.process_date as date)) as is_partition_date_shifted,
        r._batch_id, r._source_file, r._ingested_at, r._rn
    from ranked r
)
select * exclude (_rn),
    case
        when interaction_id is null then 'null_primary_key'
        when _rn > 1 then 'duplicate_interaction_id'
        when interaction_ts is null
          or event_date not between date '2023-06-17' and date '2026-06-17' then 'interaction_date_out_of_range'
        when duration_seconds < 0 or wait_time_seconds < 0 then 'negative_duration'
        when customer_id not in (select customer_id from {{ ref('customers') }}) then 'orphan_customer'
        when agent_id is not null and agent_id not in (select agent_id from {{ ref('service_agents') }}) then 'orphan_agent'
    end as quarantine_reason
from typed
