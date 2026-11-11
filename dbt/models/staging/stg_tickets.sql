-- Silver: support tickets with proper types. One row per ticket.

select
    ticket_id,
    account_id,
    contact_id,
    cast(created_at as timestamp) as created_at,
    cast(cast(created_at as timestamp) as date) as created_date,
    priority,
    priority in ('high', 'urgent') as is_high_priority,
    category,
    subject,
    body,
    status,
    cast(resolved_at as timestamp) as resolved_at
from {{ source('bronze', 'tickets') }}
