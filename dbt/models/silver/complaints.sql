select * exclude (quarantine_reason) from {{ ref("complaints_checked") }} where quarantine_reason is null
