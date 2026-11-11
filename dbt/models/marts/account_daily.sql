-- Gold: THE production table. One row per account per day.
-- Everything downstream (signals, models, the rules engine, the agents, the app)
-- reads accounts from here and nowhere else.
--
-- Contract: contracts/account_daily.yaml (owner, grain, columns, freshness, change policy).
-- Phase 3 adds the health score and the lifecycle stage to this table.

select *
from {{ ref('int_account_daily_base') }}
