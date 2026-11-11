-- Silver: tasks handed to people (CTAs). One row per task.
-- The handoff packet itself stays in the operational store; metrics only need the facts.

select
    cta_id,
    account_id,
    play_id,
    enrollment_id,
    source,
    queue,
    priority,
    reason_code,
    status,
    cast(created_on as date) as created_on,
    cast(sla_due_on as date) as sla_due_on,
    cast(picked_up_on as date) as picked_up_on,
    cast(resolved_on as date) as resolved_on,
    outcome,
    next_state
from {{ source('bronze', 'ops_ctas') }}