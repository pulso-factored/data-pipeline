{{ config(alias='customer_digital_summary') }}
-- depends_on: {{ ref('pseudonym_map') }}
-- depends_on: {{ ref('field_classification') }}
-- depends_on: {{ ref('customer_digital_summary') }}
{{ masked_select('customer_digital_summary') }}
