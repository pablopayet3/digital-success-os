-- Silver: CRM opportunities with proper types. One row per opportunity.

select
    opportunity_id,
    account_id,
    type as opportunity_type,
    name as opportunity_name,
    stage,
    stage in ('open', 'negotiation') as is_open,
    cast(amount as integer) as amount,
    cast(created_at as date) as created_at,
    cast(close_date as date) as close_date,
    owner,
    source
from {{ source('bronze', 'crm_opportunities') }}
