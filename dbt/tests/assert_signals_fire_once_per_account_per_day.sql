-- A signal is either firing for an account on a day or it is not: never twice.

select account_id, snapshot_date, signal_id, count(*) as row_count
from {{ ref('signals') }}
group by account_id, snapshot_date, signal_id
having count(*) > 1
