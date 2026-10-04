{{ config(alias="satisfaction_surveys") }}
select * from {{ ref("satisfaction_surveys_checked") }} where quarantine_reason is not null
