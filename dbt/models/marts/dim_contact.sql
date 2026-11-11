-- Gold: one row per contact, with the two flags every play checks before a touch.

select
    contacts.*,
    -- consent and a working address: the only people a journey may email
    (contacts.consent_status = 'opted_in' and contacts.email_valid) as can_email,
    -- an admin we can actually reach: the person onboarding plays are aimed at
    (contacts.persona = 'admin' and contacts.email_valid) as is_valid_admin
from {{ ref('stg_contacts') }} as contacts
