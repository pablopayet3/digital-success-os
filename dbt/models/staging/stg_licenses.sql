-- Silver: daily licence snapshot. One row per account per day while the account is active.
-- This table is the "spine" of the warehouse: it defines which account-days exist.

select
    cast(date as date) as snapshot_date,
    account_id,
    edition,
    cast(seats_licensed as integer) as seats_licensed,
    cast(seats_assigned as integer) as seats_assigned
from {{ source('bronze', 'licenses') }}
