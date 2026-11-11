-- Monthly active users cannot exceed assigned seats (10% tolerance for timing).
-- If this fails, user ids or seat counts are wrong somewhere upstream.

select account_id, snapshot_date, mau_30d, seats_assigned
from {{ ref('account_daily') }}
where mau_30d > seats_assigned * 1.1
