{# Mart de calidad: filas válidas vs cuarentena por tabla y motivo. Nada se borra de bronze. #}
with all_rows as (
    select 'customers' as table_name, quarantine_reason from {{ ref('customers_checked') }}
    union all select 'products', quarantine_reason from {{ ref('products_checked') }}
    union all select 'complaints', quarantine_reason from {{ ref('complaints_checked') }}
    union all select 'transactions', quarantine_reason from {{ ref('transactions_checked') }}
    union all select 'interactions', quarantine_reason from {{ ref('interactions_checked') }}
    union all select 'call_transcripts', quarantine_reason from {{ ref('call_transcripts_checked') }}
    union all select 'satisfaction_surveys', quarantine_reason from {{ ref('satisfaction_surveys_checked') }}
    union all select 'campaign_sends', quarantine_reason from {{ ref('campaign_sends_checked') }}
    union all select 'digital_events', quarantine_reason from {{ ref('digital_events_checked') }}
)
select
    table_name,
    coalesce(quarantine_reason, 'valid')                           as outcome,
    count(*)                                                       as rows,
    round(100.0 * count(*) / sum(count(*)) over (partition by table_name), 4) as pct_of_table
from all_rows
group by 1, 2
