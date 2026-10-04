select * exclude (quarantine_reason) from {{ ref("satisfaction_surveys_checked") }} where quarantine_reason is null
