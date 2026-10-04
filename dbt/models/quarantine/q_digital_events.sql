{{ config(materialized='view', alias='digital_events') }}
select * from {{ ref('digital_events_checked') }} where quarantine_reason is not null
