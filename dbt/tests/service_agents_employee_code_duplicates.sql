-- El diccionario declara employee_code UNIQUE NOT NULL, pero agentes distintos lo comparten (13 códigos, ~15.8K
-- interacciones). No se descartan (sus interacciones quedarían huérfanas): se marcan con employee_code_is_duplicated.
-- Aviso para enterarse si crece. Nunca usar employee_code como llave.
{{ config(severity='warn') }}
select employee_code, count(*) as agents
from {{ ref('service_agents') }}
group by 1
having count(*) > 1
