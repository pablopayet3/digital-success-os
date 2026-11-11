-- The grain of the production table: exactly one row per account per day.
-- A test passes when it returns no rows.

select account_id, snapshot_date, count(*) as row_count
from {{ ref('account_daily') }}
group by account_id, snapshot_date
having count(*) > 1
