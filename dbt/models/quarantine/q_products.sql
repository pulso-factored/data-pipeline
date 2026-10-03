{{ config(alias='products') }}
select * from {{ ref("products_checked") }} where quarantine_reason is not null
