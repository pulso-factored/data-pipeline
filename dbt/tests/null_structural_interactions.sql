-- Nulos estructurales de interactions: la duración solo existe en llamadas y video, la espera solo en llamadas entrantes.
-- Dentro de lo aplicable no debe faltar (0% observado); fuera de lo aplicable no debe venir informada.
select interaction_id, interaction_type, duration_seconds, wait_time_seconds
from {{ ref('interactions') }}
where (interaction_type in ('Chat', 'Email') and duration_seconds is not null)
   or (interaction_type in ('Inbound Call', 'Outbound Call', 'Video') and duration_seconds is null)
   or (interaction_type <> 'Inbound Call' and wait_time_seconds is not null)
   or (interaction_type = 'Inbound Call' and wait_time_seconds is null)
