-- El PDF promete ~2% de duplicados pero data/ trae 0 por PK. Si aparecen, esto debe fallar
-- ruidosamente (severity warn: la cuarentena ya los aísla, pero hay que enterarse).
{{ config(severity='warn') }}
select 'customers' as tbl, count(*) - count(distinct customer_id) as dup_rows from {{ bronze('customers') }}
having count(*) - count(distinct customer_id) > 0
union all
select 'complaints', count(*) - count(distinct complaint_id) from {{ bronze('complaints', partitioned=true) }}
having count(*) - count(distinct complaint_id) > 0
