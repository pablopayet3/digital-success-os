-- Gold: one row per account, as it stands today.

with open_renewals as (

    select
        account_id,
        bool_or(stage = 'negotiation') as renewal_in_negotiation
    from {{ ref('stg_opportunities') }}
    where opportunity_type = 'renewal' and is_open
    group by account_id

)

select
    accounts.*,
    {{ days_between('accounts.contract_start', as_of_date()) }} as account_age_days,
    {{ days_between(as_of_date(), 'accounts.renewal_date') }} as days_to_renewal,
    -- plays must stay away from an account whose renewal is being negotiated
    coalesce(open_renewals.renewal_in_negotiation, false) as renewal_in_negotiation
from {{ ref('stg_accounts') }} as accounts
left join open_renewals
    on accounts.account_id = open_renewals.account_id
