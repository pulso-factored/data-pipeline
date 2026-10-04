{{ config(materialized='view', alias='campaign_sends') }}
select * from {{ ref('campaign_sends_checked') }} where quarantine_reason is not null
