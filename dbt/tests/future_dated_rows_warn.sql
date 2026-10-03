-- last_updated posterior al corte del dataset: ~6% en customers y products (hasta +1 año). Se marca, no se descarta.
-- Aviso para enterarse si el porcentaje cambia mucho entre entregas.
{{ config(severity='warn', warn_if='> 0') }}
select 'customers' as tbl, count(*) as rows from {{ ref('customers') }} where is_last_updated_future having count(*) > 0.10 * (select count(*) from {{ ref('customers') }})
union all
select 'products', count(*) from {{ ref('products') }} where is_last_updated_future having count(*) > 0.10 * (select count(*) from {{ ref('products') }})
