-- Una sesión nunca tiene más de un cliente (0 observadas). Es la condición que hace SEGURA la derivación del cliente de
-- los eventos sin customer_id dentro de una sesión mixta; si aparece una sesión con dos clientes, hay que revisarla.
select session_id, n_distinct_customers
from {{ ref('digital_sessions') }}
where n_distinct_customers > 1
