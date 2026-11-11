-- Silver: lifecycle emails and what the recipient did. One row per email sent.

select
    send_id,
    campaign,
    subject,
    contact_id,
    account_id,
    cast(sent_at as timestamp) as sent_at,
    cast(cast(sent_at as timestamp) as date) as sent_date,
    cast(delivered as boolean) as delivered,
    cast(bounced as boolean) as bounced,
    cast(opened_at as timestamp) as opened_at,
    cast(clicked_at as timestamp) as clicked_at,
    cast(unsubscribed as boolean) as unsubscribed
from {{ source('bronze', 'email_engagement') }}
