{# Read-model por cliente con PII en claro y clasificada. SOLO para tools autenticadas de agent-core:
   las vistas de M7 enmascaran/tokenizan según field_classification. Una fila por customer_id. #}
select
    customer_id, document_type, document_number, first_name, last_name, date_of_birth, gender,
    email, mobile_phone, landline_phone, address, city, state, country_iso2, postal_code,
    segment, customer_status, credit_score, estimated_monthly_income, registration_date,
    accepts_marketing, detected_accent, branch_link_valid,
    is_missing_credit_score, is_missing_income, is_missing_accent, is_missing_email, is_missing_mobile_phone,
    last_updated
from {{ ref('customers') }}
