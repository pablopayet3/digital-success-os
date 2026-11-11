-- Gold: how handoffs to people are going. One row per queue, reason and source.
-- Definitions are in docs/human-fallback.md and docs/metrics.md.

{{ config(tags=['scored']) }}

with tasks as (

    select
        ctas.*,
        {{ days_between('created_on', 'picked_up_on') }} as days_to_pickup,
        coalesce(picked_up_on, {{ as_of_date() }}) > sla_due_on as sla_breached
    from {{ ref('stg_ops_ctas') }} as ctas

)

select
    queue,
    reason_code,
    source,
    count(*) as handoffs,
    sum(case when status = 'resolved' then 1 else 0 end) as closed,
    sum(case when status <> 'resolved' then 1 else 0 end) as open_now,
    avg(days_to_pickup) as avg_days_to_pickup,
    sum(case when sla_breached then 1 else 0 end) as sla_breaches,
    -- closed with a good result for the customer or the business
    sum(case when outcome in ('resolved', 'saved', 'expansion_opportunity') then 1 else 0 end)
        as converted,
    -- a person judged that the agent should have dealt with it
    sum(case when outcome = 'agent_should_have_handled' then 1 else 0 end) as unnecessary
from tasks
group by queue, reason_code, source