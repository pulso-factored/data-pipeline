{{ config(materialized='view', alias="interactions") }}
select * from {{ ref("interactions_checked") }} where quarantine_reason is not null
