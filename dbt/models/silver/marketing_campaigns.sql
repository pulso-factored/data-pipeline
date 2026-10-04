{# Dimensión de campañas (200 filas). Los nulos de target_* y budget son opcionales en el diccionario. #}
select
    nullif(trim(campaign_id), '')                       as campaign_id,
    campaign_name,
    nullif(description, '')                             as description,
    campaign_type,
    campaign_objective,
    nullif(promoted_product, '')                        as promoted_product,
    nullif(target_segment, '')                          as target_segment,
    nullif(target_country, '')                          as target_country,
    try_cast(start_date as date)                        as start_date,
    try_cast(end_date as date)                          as end_date,
    try_cast(budget as decimal(12,2))                   as budget,
    campaign_status,
    try_cast(expected_conversion_rate as decimal(5,2))  as expected_conversion_rate,
    _batch_id, _source_file, _ingested_at
from {{ bronze('marketing_campaigns') }}
where nullif(trim(campaign_id), '') is not null
