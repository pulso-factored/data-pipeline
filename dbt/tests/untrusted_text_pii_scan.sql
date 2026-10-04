-- Barrido de PII dentro de campos untrusted_text (emails y secuencias de 6+ dígitos, con los mismos criterios
-- conservadores que el detector de agent-core M7). El texto libre que llegue con PII real debe tokenizarse en
-- runtime (M7); aquí se mide para enterarse y para que el mart de calidad lo reporte. Aviso, no bloqueo.
{{ config(severity='warn') }}
with texts as (
    select 'turns.text' as field, text as value from {{ ref('turns') }}
    union all select 'copilot_queries.question_text', question_text from {{ ref('copilot_queries') }}
    union all select 'copilot_queries.answer', answer from {{ ref('copilot_queries') }}
    union all select 'approvals.decision_note', decision_note from {{ ref('approvals') }}
    union all select 'complaints.description', description from {{ ref('complaints') }}
    union all select 'complaints.resolution', resolution from {{ ref('complaints') }}
    union all select 'call_transcripts.customer_text', customer_text from {{ ref('call_transcripts') }}
    union all select 'call_transcripts.agent_text', agent_text from {{ ref('call_transcripts') }}
    union all select 'call_transcripts.mentioned_entities', mentioned_entities from {{ ref('call_transcripts') }}
    union all select 'satisfaction_surveys.open_comments', open_comments from {{ ref('satisfaction_surveys') }}
)
select field, count(*) as rows_with_pii
from texts
where value is not null
  and (regexp_matches(value, '[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9.-]+')
       or regexp_matches(regexp_replace(value, '[ .,\-]', '', 'g'), '[0-9]{6,}'))
group by 1
