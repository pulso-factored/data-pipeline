{# Lee la zona del evaluador. Solo existe dentro de la zona del evaluador (macros_eval, models/eval, tests/eval): el test test_no_label_leak impide referenciarla fuera. #}
{% macro bronze_eval(table) -%}
  read_parquet('{{ var("pipeline_root") }}/bronze_eval/e0/{{ table }}.parquet')
{%- endmacro %}
