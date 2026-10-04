{{ config(materialized='table') }}
{# table, no view: silver, cuarentena y los marts de calidad la leen; una vista la recalcularía en cada uno #}
{# Tipado + normalización + banderas de nulo. Dedup por PK (gana el último ingestado).
   branch_link_valid es una bandera, NO motivo de cuarentena: el diccionario promete la FK
   pero 149.995/150.000 no enlazan; descartar filas dejaría la dimensión vacía. #}
with ranked as (
    select *, row_number() over (
        partition by customer_id order by try_cast(last_updated as timestamp) desc nulls last, _ingested_at desc
    ) as _rn
    from {{ bronze('customers') }}
),
typed as (
    select
        nullif(trim(r.customer_id), '')                          as customer_id,
        r.document_number,
        d.canonical                                              as document_type,
        r.first_name,
        r.last_name,
        try_cast(r.date_of_birth as date)                        as date_of_birth,
        r.gender,
        r.email,
        r.mobile_phone,
        r.landline_phone,
        r.address,
        r.city,
        r.state,
        c.iso2                                                   as country_iso2,
        r.postal_code,
        nullif(r.detected_accent, '')                            as detected_accent,
        r.segment,
        try_cast(r.credit_score as integer)                      as credit_score,
        try_cast(r.estimated_monthly_income as decimal(12,2))    as estimated_monthly_income,
        r.occupation,
        r.marital_status,
        r.education_level,
        try_cast(r.registration_date as timestamp)               as registration_date,
        r.registration_branch_id,
        r.customer_status,
        try_cast(r.last_updated as timestamp)                    as last_updated,
        lower(r.accepts_marketing) = 'true'                      as accepts_marketing,
        (b.branch_id is not null)                                as branch_link_valid,
        (try_cast(r.last_updated as timestamp) > timestamp '{{ var("dataset_cutoff") }}') as is_last_updated_future,
        (r.credit_score is null or r.credit_score = '')          as is_missing_credit_score,
        (r.estimated_monthly_income is null or r.estimated_monthly_income = '') as is_missing_income,
        (r.detected_accent is null or r.detected_accent = '')    as is_missing_accent,
        (r.email is null or r.email = '')                        as is_missing_email,
        (r.mobile_phone is null or r.mobile_phone = '')          as is_missing_mobile_phone,
        r._batch_id, r._source_file, r._ingested_at
    from ranked r
    left join {{ ref('ref_country') }} c on c.raw_value = r.country
    left join {{ ref('ref_document_type') }} d on d.raw_value = r.document_type
    left join {{ bronze('branches') }} b on b.branch_id = r.registration_branch_id
    where r._rn = 1
)
select *,
    case
        when customer_id is null then 'null_primary_key'
        when country_iso2 is null then 'unknown_country'
        when document_type is null then 'unknown_document_type'
        when date_of_birth is null or date_of_birth > current_date or date_of_birth < date '1900-01-01' then 'invalid_date_of_birth'
        when credit_score is not null and credit_score not between 300 and 850 then 'credit_score_out_of_range'
    end as quarantine_reason
from typed
