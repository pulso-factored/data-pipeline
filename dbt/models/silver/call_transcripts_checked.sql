{{ config(materialized='table') }}
{# table, no view: silver, cuarentena y los marts de calidad la leen; una vista la recalcularía en cada uno #}
{# Transcripciones: un bloque de texto por llamada, sin hora por mensaje (por eso NO se convierten en turns del
   contrato: turn.event_time es obligatorio). El texto es untrusted_text; mentioned_entities (JSON) puede traer PII. #}
with ranked as (
    select *, row_number() over (partition by transcript_id order by _ingested_at desc) as _rn
    from {{ bronze('call_transcripts', partitioned=true) }}
),
typed as (
    select
        nullif(trim(r.transcript_id), '')                    as transcript_id,
        r.interaction_id,
        try_cast(r.process_date as date)                     as process_date,
        r.customer_id,
        nullif(r.agent_id, '')                               as agent_id,
        r.full_text,                                         -- untrusted_text
        nullif(r.customer_text, '')                          as customer_text,   -- untrusted_text
        nullif(r.agent_text, '')                             as agent_text,      -- untrusted_text
        r.detected_language,
        nullif(r.detected_accent, '')                        as detected_accent,
        try_cast(r.accent_confidence as decimal(3,2))        as accent_confidence,
        nullif(r.detected_keywords, '')                      as detected_keywords,
        nullif(r.mentioned_entities, '')                     as mentioned_entities,  -- untrusted_text
        nullif(r.detected_intents, '')                       as detected_intents,
        nullif(r.main_topics, '')                            as main_topics,
        r.transcription_model,
        nullif(r.audio_quality, '')                          as audio_quality,
        try_cast(r.duration_seconds as integer)              as duration_seconds,
        r._batch_id, r._source_file, r._ingested_at, r._rn
    from ranked r
)
select * exclude (_rn),
    case
        when transcript_id is null then 'null_primary_key'
        when _rn > 1 then 'duplicate_transcript_id'
        when full_text is null or trim(full_text) = '' then 'empty_text'
        when interaction_id not in (select interaction_id from {{ ref('interactions') }}) then 'orphan_interaction'
    end as quarantine_reason
from typed
