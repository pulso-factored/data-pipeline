-- El seudónimo de E0 (PSN-) debe corresponder a un único cliente real del banco.
select source_customer_id, count(distinct customer_id) as customers
from {{ ref('cases') }}
where source_system = 'e0_sample'
group by 1
having count(distinct customer_id) > 1
