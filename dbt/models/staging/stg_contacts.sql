-- Silver: CRM contacts, cleaned. One row per person per account.
-- Emails are lowercased, the persona tag is normalised to four standard values,
-- and a person entered twice (same email on the same account) is kept once.

with cleaned as (

    select
        contact_id,
        account_id,
        full_name,
        lower(trim(email)) as email,
        case
            when lower(trim(persona)) in ('admin', 'administrator', 'workspace admin') then 'admin'
            when lower(trim(persona)) in ('billing', 'billing contact', 'finance') then 'billing'
            when lower(trim(persona)) in ('champion', 'champ') then 'champion'
            when lower(trim(persona)) in ('end_user', 'end user', 'end-user', 'enduser', 'user') then 'end_user'
            else 'unknown'
        end as persona,
        persona as persona_raw,
        role,
        consent_status,
        cast(email_valid as boolean) as email_valid,
        product_user_id,
        cast(last_engaged_at as timestamp) as last_engaged_at
    from {{ source('bronze', 'crm_contacts') }}

),

ranked as (

    select
        *,
        row_number() over (partition by account_id, email order by contact_id) as copy_number
    from cleaned

)

select * exclude (copy_number)
from ranked
where copy_number = 1
