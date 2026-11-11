-- Silver: NPS responses with proper types. One row per response.

select
    response_id,
    account_id,
    contact_id,
    cast(score as integer) as score,
    case
        when cast(score as integer) >= 9 then 'promoter'
        when cast(score as integer) >= 7 then 'passive'
        else 'detractor'
    end as nps_band,
    comment,
    cast(responded_at as timestamp) as responded_at,
    cast(cast(responded_at as timestamp) as date) as responded_date
from {{ source('bronze', 'nps') }}
