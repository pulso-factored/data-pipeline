{{ config(materialized='view') }}
select * exclude (quarantine_reason) from {{ ref('transactions_checked') }} where quarantine_reason is null
