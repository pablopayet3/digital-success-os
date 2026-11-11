-- Gold: how the onboarding agent's conversations ended. One row per origin (a play, or
-- the mailbox), prompt version, outcome and reason.

{{ config(tags=['scored']) }}

select
    coalesce(play_id, 'mailbox') as origin,
    prompt_version,
    outcome,
    coalesce(reason_code, 'answered') as reason_code,
    coalesce(escalated_by, 'not_escalated') as escalated_by,
    count(*) as conversations,
    avg(customer_turns) as avg_customer_turns,
    sum(llm_calls) as llm_calls,
    sum(cost_usd) as cost_usd
from {{ ref('stg_ops_conversations') }}
group by
    coalesce(play_id, 'mailbox'),
    prompt_version,
    outcome,
    coalesce(reason_code, 'answered'),
    coalesce(escalated_by, 'not_escalated')