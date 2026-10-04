{# Perfil de nulos por columna de un modelo (ignora metadatos de lineage que empiezan con "_").
   Una sola pasada por la tabla: se cuenta cada columna en el mismo SELECT y luego se despliega por columna. #}
{% macro null_profile(model_name) -%}
  {%- set rel = ref(model_name) -%}
  {%- set cols = adapter.get_columns_in_relation(rel) -%}
  {%- set cols = cols | rejectattr('name', 'in', ['_batch_id', '_source_file', '_ingested_at']) | list -%}
  (
    with s as (
      select count(*) as total_rows
      {%- for c in cols %}, count("{{ c.name }}") as c{{ loop.index0 }}{% endfor %}
      from {{ rel }}
    )
    {% for c in cols -%}
    select '{{ model_name }}' as table_name, '{{ c.name }}' as column_name, total_rows, total_rows - c{{ loop.index0 }} as null_rows from s
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
  )
{%- endmacro %}
