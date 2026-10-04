{{ config(materialized='table') }}
{# table, no view: silver, cuarentena y los marts de calidad la leen; una vista la recalcularía en cada uno #}
{# product_number debe ser único (6 duplicados observados): gana el último actualizado, el resto a cuarentena. #}
with typed as (
    select
        nullif(trim(p.product_id), '')                       as product_id,
        p.customer_id,
        t.canonical                                          as product_type,
        p.product_number,
        p.currency,
        try_cast(p.current_balance as decimal(15,2))         as current_balance,
        try_cast(p.credit_limit as decimal(15,2))            as credit_limit,
        try_cast(p.interest_rate as decimal(5,2))            as interest_rate,
        try_cast(p.opening_date as date)                     as opening_date,
        try_cast(p.expiration_date as date)                  as expiration_date,
        p.opening_branch_id,
        p.product_status,
        p.opening_channel,
        lower(p.has_linked_app) = 'true'                     as has_linked_app,
        try_cast(p.days_past_due as integer)                 as days_past_due,
        try_cast(p.last_transaction_date as timestamp)       as last_transaction_date,
        try_cast(p.last_updated as timestamp)                as last_updated,
        coalesce(t.has_credit_limit, false)                  as credit_limit_applicable,
        (try_cast(p.last_updated as timestamp) > timestamp '{{ var("dataset_cutoff") }}') as is_last_updated_future,
        -- Faltante REAL: el producto debería tener cupo (tarjeta de crédito, préstamos) y no lo trae. Si el producto no
        -- lleva cupo (credit_limit_applicable = false) el nulo es NO APLICA y esta bandera es false.
        (coalesce(t.has_credit_limit, false) and (p.credit_limit is null or p.credit_limit = '')) as is_missing_credit_limit,
        p._batch_id, p._source_file, p._ingested_at,
        row_number() over (partition by p.product_id order by try_cast(p.last_updated as timestamp) desc nulls last, p._ingested_at desc) as _rn_id,
        row_number() over (partition by p.product_number order by try_cast(p.last_updated as timestamp) desc nulls last, p.product_id) as _rn_number
    from {{ bronze('products') }} p
    left join {{ ref('ref_product_type') }} t on t.raw_value = p.product_type
)
select * exclude (_rn_id, _rn_number),
    case
        when product_id is null then 'null_primary_key'
        when _rn_id > 1 then 'duplicate_product_id'
        when product_type is null then 'unknown_product_type'
        when product_number is null then 'null_product_number'
        when _rn_number > 1 then 'duplicate_product_number'
        when customer_id not in (select customer_id from {{ ref('customers') }}) then 'orphan_customer'
    end as quarantine_reason
from typed
