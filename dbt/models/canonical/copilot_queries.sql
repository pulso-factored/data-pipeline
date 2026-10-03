{# `copilot_query`. question_text y answer son untrusted_text. #}
select
    query_id, case_id, analyst_id, event_time, question_text, query_signature,
    from_json(tables_read, '["VARCHAR"]')            as tables_read,
    from_json(columns_read, '["VARCHAR"]')           as columns_read,
    answered_by, answer, sent_to_chat,
    'e0_sample'                                      as source_system
from {{ bronze_e0('copilot_query') }}
