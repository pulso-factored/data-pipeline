-- Nulos estructurales de transactions (el 5% restante dentro de los tipos aplicables es faltante real):
--   merchant/categoría solo aplican a purchase y payment; sucursal solo a atm y branch.
select transaction_id, transaction_type, channel
from {{ ref('transactions') }}
where (transaction_type not in ('purchase', 'payment') and (merchant_name is not null or transaction_category is not null))
   or (channel not in ('atm', 'branch') and branch_id is not null)
