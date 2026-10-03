{{ config(materialized='view', alias='transactions') }}
select * from {{ ref('transactions_checked') }} where quarantine_reason is not null
