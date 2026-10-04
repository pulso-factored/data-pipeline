{# Frescura por fuente: último dato de negocio y última ingesta. Política: el reto es estático, así que
   (customers/products usan registration_date/opening_date: last_updated tiene ~6% de fechas futuras) la frescura se mide contra el corte del dataset (2026-06-17) y la ingesta contra el último batch. #}
select 'customers' as source_table, max(registration_date) as latest_business_ts, max(_ingested_at) as latest_ingested_at, count(*) as rows from {{ ref('customers') }}
union all select 'products', cast(max(opening_date) as timestamp), max(_ingested_at), count(*) from {{ ref('products') }}
union all select 'complaints', max(creation_date), max(_ingested_at), count(*) from {{ ref('complaints') }}
union all select 'transactions', max(transaction_ts), max(_ingested_at), count(*) from {{ ref('transactions') }}
union all select 'interactions', max(interaction_ts), max(_ingested_at), count(*) from {{ ref('interactions') }}
union all select 'campaign_sends', max(send_ts), max(_ingested_at), count(*) from {{ ref('campaign_sends') }}
union all select 'digital_events', max(event_ts), max(_ingested_at), count(*) from {{ ref('digital_events') }}
union all select 'e0_cases', max(opened_at), max(_ingested_at), count(*) from {{ ref('stg_e0_case') }}
