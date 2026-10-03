{{ config(alias='customer_products') }}
-- depends_on: {{ ref('pseudonym_map') }}
-- depends_on: {{ ref('field_classification') }}
-- depends_on: {{ ref('customer_products') }}
{{ masked_select('customer_products') }}
