select * exclude (quarantine_reason) from {{ ref("products_checked") }} where quarantine_reason is null
