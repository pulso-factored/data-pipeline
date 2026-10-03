{# Tabla canónica `case` del contrato platform_history, con source_system. #}
select * from {{ ref('stg_e0_case') }}
union all by name
select * from {{ ref('stg_bank_case') }}
