{# Transacciones válidas por cliente (consulta por customer_id). amount_usd_source dice si el USD es
   reportado o derivado (aproximado ~1%). Sin latitud/longitud (casi siempre vacías y de alta resolución). #}
select
    transaction_id, customer_id, product_id, transaction_ts, event_date, transaction_type,
    transaction_category, amount, currency, amount_usd, amount_usd_source, channel,
    merchant_name, merchant_category, transaction_country_iso2, transaction_city,
    transaction_status, response_code, is_fraud, fraud_score, product_quarantined
from {{ ref('transactions') }}
