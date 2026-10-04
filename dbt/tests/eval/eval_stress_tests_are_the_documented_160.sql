{{ config(enabled=var('build_eval', false)) }}
-- README de E0: 100 casos en portugues y 60 dificiles son pruebas de estres (labels.stress_test), y se reportan aparte.
select 'stress_total' as check_name, count(*) as n from {{ ref('labels') }} where stress_test is not null having count(*) <> 160
union all
select 'portuguese', count(*) from {{ ref('labels') }} where stress_test = 'idioma_pt' having count(*) <> 100
union all
select 'hard_cases', count(*) from {{ ref('labels') }} where hard_case is not null having count(*) <> 60
union all
select 'portuguese_language_mismatch', count(*) from {{ ref('labels') }} where (language = 'pt') <> (stress_test = 'idioma_pt') having count(*) > 0
