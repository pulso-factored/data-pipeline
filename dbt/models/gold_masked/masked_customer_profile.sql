{{ config(alias='customer_profile') }}
-- depends_on: {{ ref('pseudonym_map') }}
-- depends_on: {{ ref('field_classification') }}
-- depends_on: {{ ref('customer_profile') }}
{{ masked_select('customer_profile') }}
