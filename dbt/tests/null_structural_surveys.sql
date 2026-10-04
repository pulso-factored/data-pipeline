-- nps_category solo aplica a las encuestas NPS; en CSAT y CES debe venir siempre vacía.
select survey_id, survey_type, nps_category
from {{ ref('satisfaction_surveys') }}
where survey_type <> 'NPS' and nps_category is not null
