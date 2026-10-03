{# Genera el SELECT enmascarado de un modelo de gold_restricted a partir de las reglas del seed field_classification.
   Una sola fuente de verdad: si cambia la clasificación de una columna, cambia su enmascarado.

   pii_direct  -> parcial según el tag; customer_id se reemplaza por customer_pseudo (HMAC, enlazable con gold_analytics)
   pii_quasi   -> se elimina la columna, salvo date_of_birth -> age_bucket (rango de 10 años al corte del dataset)
   untrusted   -> se limpian emails y secuencias largas de dígitos
   financial / public -> pasan
   Las columnas pii_direct enmascaradas se renombran con sufijo _masked: así ninguna columna publicada se llama
   como un campo pii_direct y la guardia de publicación puede verificarlo por nombre. #}
{% macro mask_expr(col, cls, tag, qop) -%}
  {%- if cls == 'pii_direct' -%}
    {%- if tag == 'name' -%}substr({{ col }}, 1, 1) || '***'
    {%- elif tag in ('doc', 'tel', 'prod') -%}'***' || right({{ col }}, 4)
    {%- elif tag == 'email' -%}substr({{ col }}, 1, 1) || '***@***'
    {%- else -%}case when {{ col }} is null then null else '[oculto]' end
    {%- endif -%}
  {%- elif cls == 'untrusted_text' -%}
    regexp_replace(regexp_replace({{ col }}, '[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9.-]+', '[email]', 'g'), '[0-9][0-9 .,-]{4,}[0-9]', '[num]', 'g')
  {%- else -%}{{ col }}
  {%- endif -%}
{%- endmacro %}

{% macro masked_select(model_name, source_schema='gold_restricted') -%}
  {%- set rel = ref(model_name) -%}
  {%- set fc = ref('field_classification') -%}
  {%- if execute -%}
    {%- set cols = adapter.get_columns_in_relation(rel) -%}
    {%- set rules = {} -%}
    {%- for r in run_query("select column_name, class, tag, quasi_op from " ~ fc ~ " where schema_name = '" ~ source_schema ~ "' and table_name = '" ~ model_name ~ "'").rows -%}
      {%- do rules.update({r[0]: {'cls': r[1], 'tag': r[2], 'qop': r[3]}}) -%}
    {%- endfor -%}
    select
    {%- set ns = namespace(first=true) -%}
    {%- for c in cols %}
      {%- set rule = rules.get(c.name) -%}
      {%- if rule is none -%}
        {{ exceptions.raise_compiler_error("Columna sin clasificar en " ~ model_name ~ ": " ~ c.name) }}
      {%- endif -%}
      {%- if c.name == 'customer_id' -%}
        {{ ',' if not ns.first }} pm.customer_pseudo
        {%- set ns.first = false -%}
      {%- elif rule.cls == 'pii_quasi' and c.name == 'date_of_birth' -%}
        {{ ',' if not ns.first }} cast(floor(date_diff('year', r.date_of_birth, date '{{ var("dataset_cutoff") }}') / 10) * 10 as integer) || '-' || cast(floor(date_diff('year', r.date_of_birth, date '{{ var("dataset_cutoff") }}') / 10) * 10 + 9 as integer) as age_bucket
        {%- set ns.first = false -%}
      {%- elif rule.cls == 'pii_quasi' -%}
        {# se elimina #}
      {%- elif rule.cls == 'pii_direct' -%}
        {{ ',' if not ns.first }} {{ mask_expr('r.' ~ c.name, rule.cls, rule.tag, rule.qop) }} as {{ c.name }}_masked
        {%- set ns.first = false -%}
      {%- else -%}
        {{ ',' if not ns.first }} {{ mask_expr('r.' ~ c.name, rule.cls, rule.tag, rule.qop) }} as {{ c.name }}
        {%- set ns.first = false -%}
      {%- endif -%}
    {%- endfor %}
    from {{ rel }} r
    left join {{ ref('pseudonym_map') }} pm on pm.customer_id = r.customer_id
  {%- else -%}
    select 1
  {%- endif -%}
{%- endmacro %}
