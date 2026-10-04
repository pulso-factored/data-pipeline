{# Vista ordenada de cada caso derivada de platform_history; si difiere, manda platform_history. #}
select
    case_id, ts, kind, actor, ref_id, summary,
    from_json(evidence_ids, '["VARCHAR"]')        as evidence_ids,
    _batch_id, _contract_version, _ingested_at
from {{ bronze_eval('timeline') }}
