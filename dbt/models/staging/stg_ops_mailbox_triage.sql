-- Silver: what the mailbox triage agent did with each reply. One row per reply.

select
    message_id,
    cast(processed_on as date) as processed_on,
    account_id,
    contact_id,
    intent,
    sentiment,
    cast(confidence as double) as confidence,
    action,
    cta_id
from {{ source('bronze', 'ops_mailbox_triage') }}