{# Mart de calidad: nulos por columna con su tipo según la política (seed null_policy).
   Una columna con nulos y sin tipo asignado es un nulo SIN EXPLICAR: lo detecta un test. #}
with profile as (
    {{ null_profile('customers') }}
    union all {{ null_profile('products') }}
    union all {{ null_profile('complaints') }}
    union all {{ null_profile('transactions') }}
    union all {{ null_profile('interactions') }}
    union all {{ null_profile('service_agents') }}
    union all {{ null_profile('call_transcripts') }}
)
select
    p.table_name, p.column_name, p.total_rows, p.null_rows,
    round(100.0 * p.null_rows / nullif(p.total_rows, 0), 2) as null_pct,
    n.null_type, n.note
from profile p
left join {{ ref('null_policy') }} n using (table_name, column_name)
