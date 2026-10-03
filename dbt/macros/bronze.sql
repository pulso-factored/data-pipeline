{# Lee la capa bronze del banco. Dimensiones: un parquet; hechos: un parquet por partición diaria. #}
{% macro bronze(table, partitioned=false) -%}
  {%- if partitioned -%}
    read_parquet('{{ var("pipeline_root") }}/bronze/bank/{{ table }}/*/*/*/*.parquet', union_by_name=true)
  {%- else -%}
    read_parquet('{{ var("pipeline_root") }}/bronze/bank/{{ table }}.parquet', union_by_name=true)
  {%- endif -%}
{%- endmacro %}

{# Muestra E0 (snapshot estático). `labels` y `timeline` NO se leen desde aquí: viven en bronze_eval. #}
{% macro bronze_e0(table) -%}
  read_parquet('{{ var("pipeline_root") }}/bronze/e0/{{ table }}.parquet')
{%- endmacro %}
