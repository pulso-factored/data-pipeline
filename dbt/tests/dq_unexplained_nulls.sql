-- Todo nulo debe tener un tipo en null_policy (structural | state | derivable | missing_real | not_in_source).
-- Una columna con nulos y sin política es un nulo sin explicar: el pipeline no lo deja pasar.
select table_name, column_name, null_rows
from {{ ref('dq_null_profile') }}
where null_rows > 0 and null_type is null
