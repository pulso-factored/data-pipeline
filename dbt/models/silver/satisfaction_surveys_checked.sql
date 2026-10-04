{{ config(materialized='view') }}
{# Encuestas posteriores a la interacción. Escalas observadas más estrechas que las documentadas: CSAT 1-4 (doc 1-5),
   NPS 2-7 (doc 0-10), CES 1-4. nps_category solo existe en las encuestas NPS (nulo estructural).
   open_comments es untrusted_text. Una fila por survey_id; interaction_id puede ser nulo (FK opcional). #}
with ranked as (
    select *, row_number() over (partition by survey_id order by _ingested_at desc) as _rn
    from {{ bronze('satisfaction_surveys', partitioned=true) }}
),
typed as (
    select
        nullif(trim(r.survey_id), '')                        as survey_id,
        try_cast(r.survey_date as timestamp)                 as survey_ts,
        cast(try_cast(r.survey_date as timestamp) as date)   as event_date,
        try_cast(r.process_date as date)                     as process_date,
        nullif(r.interaction_id, '')                         as interaction_id,
        r.customer_id,
        nullif(r.agent_id, '')                               as agent_id,
        r.survey_type,
        r.send_channel,
        try_cast(r.main_score as integer)                    as main_score,
        nullif(r.nps_category, '')                           as nps_category,
        nullif(r.question_1_text, '')                        as question_1_text,
        try_cast(r.question_1_response as integer)           as question_1_response,
        nullif(r.question_2_text, '')                        as question_2_text,
        try_cast(r.question_2_response as integer)           as question_2_response,
        nullif(r.question_3_text, '')                        as question_3_text,
        try_cast(r.question_3_response as integer)           as question_3_response,
        nullif(r.open_comments, '')                          as open_comments,   -- untrusted_text
        nullif(r.comment_sentiment, '')                      as comment_sentiment,
        try_cast(r.response_time_hours as decimal(8,2))      as response_time_hours,
        try_cast(r.campaign_response_rate as decimal(5,2))   as campaign_response_rate,
        r._batch_id, r._source_file, r._ingested_at, r._rn
    from ranked r
)
select * exclude (_rn),
    case
        when survey_id is null then 'null_primary_key'
        when _rn > 1 then 'duplicate_survey_id'
        when survey_ts is null
          or event_date not between date '2023-06-17' and date '2026-06-18' then 'survey_date_out_of_range'
        when main_score is null then 'null_main_score'
        when customer_id not in (select customer_id from {{ ref('customers') }}) then 'orphan_customer'
        when agent_id is not null and agent_id not in (select agent_id from {{ ref('service_agents') }}) then 'orphan_agent'
        when interaction_id is not null and interaction_id not in (select interaction_id from {{ ref('interactions') }}) then 'orphan_interaction'
    end as quarantine_reason
from typed
