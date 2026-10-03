{{ config(alias='customer_transactions') }}
-- depends_on: {{ ref('pseudonym_map') }}
-- depends_on: {{ ref('field_classification') }}
-- depends_on: {{ ref('customer_transactions') }}
{{ masked_select('customer_transactions') }}
