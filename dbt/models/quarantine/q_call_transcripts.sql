{{ config(materialized='view', alias="call_transcripts") }}
select * from {{ ref("call_transcripts_checked") }} where quarantine_reason is not null
