select * exclude (quarantine_reason) from {{ ref("customers_checked") }} where quarantine_reason is null
