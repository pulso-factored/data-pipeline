{{ config(enabled=var('build_eval', false)) }}
-- Cada caso de E0 tiene su etiqueta y no hay etiquetas de casos que no existen.
select 'case_without_label' as violation, c.case_id
from {{ source('wh', 'cases') }} c
where c.source_system = 'e0_sample' and c.case_id not in (select case_id from {{ ref('labels') }})
union all
select 'label_without_case', l.case_id
from {{ ref('labels') }} l
where l.case_id not in (select case_id from {{ source('wh', 'cases') }} where source_system = 'e0_sample')
