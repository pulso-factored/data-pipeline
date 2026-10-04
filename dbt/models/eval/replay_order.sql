{# Orden de reproducción: se construye con split = arranque y se mide con split = reproduccion, caso por caso en orden
   de opened_at. Un componente solo puede usar casos abiertos ANTES del que se evalúa (prior_cases). #}
select
    case_id, rank, split, opened_at,
    rank - 1                                      as prior_cases
from {{ ref('labels') }}
