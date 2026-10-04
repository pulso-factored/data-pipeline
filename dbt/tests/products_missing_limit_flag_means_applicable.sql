-- is_missing_credit_limit debe significar "falta donde debería estar" (6.655 productos), NO "es nulo" (274.681).
-- Con la definición anterior valía true también en cuentas de ahorro, donde el nulo es NO APLICA, y un lector no podía
-- distinguir ambos casos. Esta prueba fija la semántica: la bandera solo existe dentro de lo aplicable.
select product_id, product_type, credit_limit_applicable, credit_limit, is_missing_credit_limit
from {{ ref('products') }}
where (is_missing_credit_limit and not credit_limit_applicable)
   or (credit_limit_applicable and credit_limit is null and not is_missing_credit_limit)
   or (credit_limit is not null and is_missing_credit_limit)
