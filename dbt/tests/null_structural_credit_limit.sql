-- Nulo estructural: credit_limit debe ser NULL cuando el producto no es de crédito.
-- (El caso inverso, crédito sin límite, es faltante real y se mide en el mart de calidad.)
select product_id, product_type, credit_limit
from {{ ref('products') }}
where credit_limit_applicable = false and credit_limit is not null
