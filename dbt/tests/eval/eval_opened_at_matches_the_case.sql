{{ config(enabled=var('build_eval', false)) }}
select l.case_id, l.opened_at as label_opened_at, c.opened_at as case_opened_at
from {{ ref('labels') }} l
join {{ source('wh', 'cases') }} c using (case_id)
where l.opened_at is distinct from c.opened_at
