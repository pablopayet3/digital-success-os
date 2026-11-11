-- Silver: replies that landed in the shared success mailbox. One row per message.
-- A reply only carries a sender address and the email it answers. The account and
-- the contact are found through that original email.

with messages as (

    select
        message_id,
        cast(received_at as timestamp) as received_at,
        lower(trim(from_email)) as from_email,
        from_name,
        to_email,
        in_reply_to as send_id,
        subject,
        body
    from {{ source('bronze', 'mailbox') }}

)

select
    messages.message_id,
    messages.received_at,
    cast(messages.received_at as date) as received_date,
    messages.from_email,
    messages.from_name,
    messages.send_id,
    sends.campaign,
    sends.account_id,
    sends.contact_id as addressed_contact_id,
    -- false when someone else answered (a colleague, or the person's other address)
    coalesce(messages.from_email = contacts.email, false) as sender_is_addressee,
    messages.subject,
    messages.body
from messages
left join {{ ref('stg_email_engagement') }} as sends
    on messages.send_id = sends.send_id
left join {{ ref('stg_contacts') }} as contacts
    on sends.contact_id = contacts.contact_id
