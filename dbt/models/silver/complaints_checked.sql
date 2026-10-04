{{ config(materialized='table') }}
{# table, no view: silver, cuarentena y los marts de calidad la leen; una vista la recalcularía en cada uno #}
{# Los nulos de resolución son de ESTADO (caso abierto), no faltantes: is_open los explica. #}
with ranked as (
    select *, row_number() over (partition by complaint_id order by _ingested_at desc) as _rn
    from {{ bronze('complaints', partitioned=true) }}
),
typed as (
    select
        nullif(trim(complaint_id), '')                       as complaint_id,
        try_cast(creation_date as timestamp)                 as creation_date,
        try_cast(process_date as date)                       as process_date,
        customer_id,
        case_type,
        category,
        nullif(subcategory, '')                              as subcategory,
        reception_channel,
        nullif(affected_product_id, '')                      as affected_product_id,
        nullif(related_branch_id, '')                        as related_branch_id,
        nullif(origin_interaction_id, '')                    as origin_interaction_id,
        description,                                         -- untrusted_text
        try_cast(claimed_amount as decimal(15,2))            as claimed_amount,
        nullif(currency, '')                                 as currency,
        lower(priority)                                      as priority,
        status,
        nullif(assigned_agent_id, '')                        as assigned_agent_id,
        try_cast(assignment_date as timestamp)               as assignment_date,
        try_cast(first_response_date as timestamp)           as first_response_date,
        try_cast(resolution_date as timestamp)               as resolution_date,
        try_cast(closing_date as timestamp)                  as closing_date,
        lower(sla_breached) = 'true'                         as sla_breached,
        try_cast(resolution_days as integer)                 as resolution_days,
        nullif(resolution, '')                               as resolution,   -- untrusted_text
        try_cast(compensation_granted as decimal(15,2))      as compensation_granted,
        try_cast(resolution_satisfaction as integer)         as resolution_satisfaction,
        lower(is_repeat_complainer) = 'true'                 as is_repeat_complainer,
        status in ('Open', 'In Process', 'Escalated')        as is_open,
        (status in ('Resolved', 'Closed') and (resolution_date is null or resolution_date = '')) as is_resolution_date_inconsistent,
        _batch_id, _source_file, _ingested_at, _rn
    from ranked
)
select * exclude (_rn),
    case
        when complaint_id is null then 'null_primary_key'
        when _rn > 1 then 'duplicate_complaint_id'
        when creation_date is null then 'invalid_creation_date'
        when resolution_date is not null and resolution_date < creation_date then 'resolution_before_creation'
        when customer_id not in (select customer_id from {{ ref('customers') }}) then 'orphan_customer'
    end as quarantine_reason
from typed
