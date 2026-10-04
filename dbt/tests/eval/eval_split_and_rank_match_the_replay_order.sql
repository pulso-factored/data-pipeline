{{ config(enabled=var('build_eval', false)) }}
-- El split y el rank de labels deben coincidir con los derivados de opened_at en gold_analytics.case_facts (sin usar labels).
-- Es la prueba de que arranque/reproduccion se puede reconstruir sin leer las respuestas.
select l.case_id, l.split as label_split, f.split as derived_split, l.rank as label_rank, f.replay_rank as derived_rank
from {{ ref('labels') }} l
join {{ source('wh_gold', 'case_facts') }} f using (case_id)
where l.split is distinct from f.split or l.rank is distinct from f.replay_rank
