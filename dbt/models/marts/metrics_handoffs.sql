-- Gold: how handoffs to people are going. One row per queue, reason and source.
-- Definitions are in docs/human-fallback.md and docs/metrics.md.

{{ config(tags=['scored']) }}

with tasks as (

    select
        ctas.*,
        {{ days_between('created_on', 'picked_up_on') }} as days_to_pickup,
        coalesce(picked_up_on, {{ as_of_date() }}) > sla_due_on as sla_breached
    from {{ ref('stg_ops_ctas') }} as ctas

),

-- A closed task was followed by a new task for the same account within 14 days.
-- That is a re-contact: the first handoff did not settle the matter.
recontacts as (

    select earlier.cta_id
    from {{ ref('stg_ops_ctas') }} as earlier
    inner join {{ ref('stg_ops_ctas') }} as later
        on earlier.account_id = later.account_id
        and earlier.cta_id <> later.cta_id
        and later.created_on > earlier.resolved_on
        and later.created_on <= {{ days_after('earlier.resolved_on', 14) }}
    where earlier.resolved_on is not null
    group by earlier.cta_id

)

select
    tasks.queue,
    tasks.reason_code,
    tasks.source,
    count(*) as handoffs,
    sum(case when tasks.status = 'resolved' then 1 else 0 end) as closed,
    sum(case when tasks.status <> 'resolved' then 1 else 0 end) as open_now,
    avg(tasks.days_to_pickup) as avg_days_to_pickup,
    -- the two parts of that average, so it can be recomputed exactly over several rows
    sum(case when tasks.picked_up_on is not null then 1 else 0 end) as picked_up,
    sum(tasks.days_to_pickup) as days_to_pickup_total,
    sum(case when tasks.sla_breached then 1 else 0 end) as sla_breaches,
    -- closed with a good result for the customer or the business
    sum(case when tasks.outcome in ('resolved', 'saved', 'expansion_opportunity') then 1 else 0 end)
        as converted,
    -- a person judged that the agent should have dealt with it
    sum(case when tasks.outcome = 'agent_should_have_handled' then 1 else 0 end) as unnecessary,
    sum(case when recontacts.cta_id is not null then 1 else 0 end) as recontacted
from tasks
left join recontacts on tasks.cta_id = recontacts.cta_id
group by tasks.queue, tasks.reason_code, tasks.source
