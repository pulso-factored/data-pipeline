-- Toda columna expuesta (silver base, canonical y gold_restricted) debe estar clasificada. Un campo sin clasificar
-- se trata como pii_direct en agent-core, pero aquí no se permite que pase sin decisión explícita.
-- Regenerar con scripts/gen_field_classification.py y revisar a mano las clases nuevas.
select c.table_schema, c.table_name, c.column_name
from information_schema.columns c
join information_schema.tables t using (table_schema, table_name)
left join {{ ref('field_classification') }} f
  on f.schema_name = c.table_schema and f.table_name = c.table_name and f.column_name = c.column_name
where t.table_type = 'BASE TABLE'
  and (c.table_schema in ('canonical', 'gold_restricted')
       or (c.table_schema = 'silver' and c.table_name in ('customers', 'products', 'complaints', 'transactions', 'exchange_rates')))
  and f.column_name is null
