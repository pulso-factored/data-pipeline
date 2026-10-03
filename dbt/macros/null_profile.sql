{# Perfil de nulos por columna de un modelo (ignora metadatos de lineage que empiezan con "_"). #}
{% macro null_profile(model_name) -%}
  {%- set rel = ref(model_name) -%}
  {%- set cols = adapter.get_columns_in_relation(rel) | selectattr('name', 'ne', None) | list -%}
  {%- set cols = cols | rejectattr('name', 'in', ['_batch_id', '_source_file', '_ingested_at']) | list -%}
  {% for c in cols %}
  select '{{ model_name }}' as table_name, '{{ c.name }}' as column_name,
         count(*) as total_rows, count(*) - count("{{ c.name }}") as null_rows
  from {{ rel }}
  {% if not loop.last %}union all{% endif %}
  {% endfor %}
{%- endmacro %}
