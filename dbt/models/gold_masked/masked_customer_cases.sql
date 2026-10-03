{{ config(alias='customer_cases') }}
-- depends_on: {{ ref('pseudonym_map') }}
-- depends_on: {{ ref('field_classification') }}
-- depends_on: {{ ref('customer_cases') }}
{{ masked_select('customer_cases') }}
