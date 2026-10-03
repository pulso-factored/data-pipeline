-- gold_analytics (seudonimizada) y gold_masked (enmascarada): ninguna columna puede llamarse como un campo pii_direct
-- (customer_id, document_number, nombres, contacto...). El cliente solo aparece como customer_pseudo.
select c.table_name, c.column_name
from information_schema.columns c
where c.table_schema in ('gold_analytics', 'gold_masked')
  and c.column_name in (
      select distinct column_name from {{ ref('field_classification') }}
      where class = 'pii_direct' and column_name <> 'customer_pseudo'
  )
