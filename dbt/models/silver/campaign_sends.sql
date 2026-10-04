{{ config(materialized='view') }}
select * exclude (quarantine_reason) from {{ ref('campaign_sends_checked') }} where quarantine_reason is null
