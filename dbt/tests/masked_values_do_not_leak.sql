-- El enmascarado debe enmascarar: ningún valor de gold_masked puede ser igual al crudo, ni mostrar más de
-- los últimos 4 caracteres de un documento, y el número de filas debe coincidir con gold_restricted.
select 'raw_value_equals_masked' as violation, count(*) as n
from {{ ref('masked_customer_profile') }} m
join {{ ref('pseudonym_map') }} pm using (customer_pseudo)
join {{ ref('customer_profile') }} r on r.customer_id = pm.customer_id
where m.document_number_masked = r.document_number or m.email_masked = r.email
   or m.address_masked = r.address or m.first_name_masked = r.first_name or m.mobile_phone_masked = r.mobile_phone
having count(*) > 0
union all
select 'document_shows_more_than_last4', count(*)
from {{ ref('masked_customer_profile') }}
where length(document_number_masked) > 7
having count(*) > 0
union all
select 'row_count_mismatch_profile', abs((select count(*) from {{ ref('masked_customer_profile') }}) - (select count(*) from {{ ref('customer_profile') }}))
where (select count(*) from {{ ref('masked_customer_profile') }}) <> (select count(*) from {{ ref('customer_profile') }})
union all
select 'row_count_mismatch_transactions', abs((select count(*) from {{ ref('masked_customer_transactions') }}) - (select count(*) from {{ ref('customer_transactions') }}))
where (select count(*) from {{ ref('masked_customer_transactions') }}) <> (select count(*) from {{ ref('customer_transactions') }})
