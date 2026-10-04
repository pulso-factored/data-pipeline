select * exclude (quarantine_reason) from {{ ref("call_transcripts_checked") }} where quarantine_reason is null
