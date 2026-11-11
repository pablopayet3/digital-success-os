-- Nothing in silver may be dated after "today" (the latest licence snapshot).

select 'stg_events' as model, count(*) as future_rows
from {{ ref('stg_events') }}
where event_date > {{ as_of_date() }}
having count(*) > 0

union all

select 'stg_tickets', count(*)
from {{ ref('stg_tickets') }}
where created_date > {{ as_of_date() }}
having count(*) > 0

union all

select 'stg_nps', count(*)
from {{ ref('stg_nps') }}
where responded_date > {{ as_of_date() }}
having count(*) > 0

union all

select 'stg_email_engagement', count(*)
from {{ ref('stg_email_engagement') }}
where sent_date > {{ as_of_date() }}
having count(*) > 0
