-- Silver: CRM accounts with proper types. One row per account.

select
    account_id,
    name as account_name,
    segment,
    coverage_tier,
    edition,
    products,
    products like '%docs%' as has_docs,
    products like '%assist%' as has_assist,
    cast(seats_licensed as integer) as seats_licensed,
    cast(arr as integer) as arr,
    cast(contract_start as date) as contract_start,
    cast(renewal_date as date) as renewal_date,
    region,
    industry,
    account_owner,
    csm,
    status,
    cast(churned_at as date) as churned_at
from {{ source('bronze', 'crm_accounts') }}
