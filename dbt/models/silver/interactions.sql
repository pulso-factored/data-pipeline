{{ config(materialized='view') }}
select * exclude (quarantine_reason) from {{ ref("interactions_checked") }} where quarantine_reason is null
