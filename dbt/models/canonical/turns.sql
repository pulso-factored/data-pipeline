{# `turn` (solo E0 por ahora). text es untrusted_text; los marcadores {NOMBRE}, {MONTO}... se conservan. #}
select
    turn_id, case_id, event_time, author_role, author_id, text, language,
    from_suggestion_id,
    from_json(evidence_ids, '["VARCHAR"]')           as evidence_ids,
    text_source,
    'e0_sample'                                      as source_system
from {{ bronze_e0('turn') }}
