{{ config(alias='customers') }}
select * from {{ ref("customers_checked") }} where quarantine_reason is not null
