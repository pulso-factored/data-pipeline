{{ config(materialized='view', alias='complaints') }}
select * from {{ ref("complaints_checked") }} where quarantine_reason is not null
