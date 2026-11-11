-- Silver: conversations the onboarding agent had. One row per conversation.
-- Transcripts stay in the operational store; metrics only need how each one ended.

select
    conversation_id,
    cast(day as date) as conversation_date,
    account_id,
    play_id,
    enrollment_id,
    scenario,
    prompt_version,
    outcome,
    reason_code,
    escalated_by,
    queue,
    cast(customer_turns as integer) as customer_turns,
    cast(llm_calls as integer) as llm_calls,
    cast(cost_usd as double) as cost_usd,
    cast(latency_ms as integer) as latency_ms,
    cta_id
from {{ source('bronze', 'ops_conversations') }}