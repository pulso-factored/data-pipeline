{# Productos por cliente. credit_limit es NULL cuando no aplica (credit_limit_applicable = false) y
   faltante real cuando aplica y es NULL (is_missing_credit_limit). #}
select
    product_id, customer_id, product_type, product_number, currency, current_balance,
    credit_limit, interest_rate, product_status, opening_date, expiration_date,
    days_past_due, last_transaction_date, credit_limit_applicable, is_missing_credit_limit
from {{ ref('products') }}
