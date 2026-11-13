-- Gold: what happened to every account that entered a play. One row per enrolment,
-- treatment and holdout alike.
--
-- Each outcome is a yes/no fact about the measurement window: the days after the
-- account entered, up to the window length set in config/plays.yaml. Which outcome is
-- a play's success metric is decided in the play config, not here. All six are
-- computed for every enrolment, so any play can also be read against a guardrail
-- (for example: did the upgrade play hurt retention?).
--
-- The window may still be open (window_complete = false). Treatment and holdout enter
-- on the same days, so comparing them "so far" is fair; the report says how many days
-- have been observed.

{{ config(tags=['scored']) }}

{% set window_days = var('measurement_window_days', 30) %}

with enrolments as (

    select
        enrollment_id,
        account_id,
        play_id,
        play_version,
        arm,
        rollout_stage,
        status,
        highest_tier,
        enrolled_on,
        {{ days_after('enrolled_on', window_days) }} as window_end
    from {{ ref('stg_ops_enrollments') }}

),

-- the account on the day it entered
at_entry as (

    select
        enrolments.enrollment_id,
        daily.segment,
        daily.edition,
        daily.arr as arr_at_entry,
        daily.mau_prior_30d as mau_before_drop
    from enrolments
    inner join {{ ref('account_daily') }} as daily
        on enrolments.account_id = daily.account_id
        and enrolments.enrolled_on = daily.snapshot_date

),

-- the account from the day after entry to the end of the window
in_window as (

    select
        enrolments.enrollment_id,
        count(*) as days_observed,
        max(daily.prerequisite_closure_pct) as best_closure,
        max(daily.mau_30d) as best_mau,
        max(case when daily.has_valid_admin then 1 else 0 end) as had_valid_admin
    from enrolments
    inner join {{ ref('account_daily') }} as daily
        on enrolments.account_id = daily.account_id
        and daily.snapshot_date > enrolments.enrolled_on
        and daily.snapshot_date <= enrolments.window_end
    group by enrolments.enrollment_id

),

docs as (

    select
        enrolments.enrollment_id,
        sum(usage.docs_published) as docs_published
    from enrolments
    inner join {{ ref('fct_usage_daily') }} as usage
        on enrolments.account_id = usage.account_id
        and usage.snapshot_date > enrolments.enrolled_on
        and usage.snapshot_date <= enrolments.window_end
    group by enrolments.enrollment_id

),

expansions as (

    select
        enrolments.enrollment_id,
        count(*) as expansions_won,
        sum(opportunities.amount) as expansion_amount
    from enrolments
    inner join {{ ref('stg_opportunities') }} as opportunities
        on enrolments.account_id = opportunities.account_id
        and opportunities.opportunity_type = 'expansion'
        and opportunities.stage = 'closed_won'
        and opportunities.close_date > enrolments.enrolled_on
        and opportunities.close_date <= enrolments.window_end
    group by enrolments.enrollment_id

),

advocacy as (

    -- The reference request was accepted: its "Yes" link was clicked in the window.
    select
        enrolments.enrollment_id,
        count(*) as accepted
    from enrolments
    inner join {{ ref('stg_email_engagement') }} as emails
        on enrolments.account_id = emails.account_id
        and emails.campaign = 'play_' || enrolments.play_id
        and emails.clicked_at is not null
        and emails.sent_date >= enrolments.enrolled_on
        and emails.sent_date <= enrolments.window_end
    group by enrolments.enrollment_id

),

outcomes as (

    select
        enrolments.enrollment_id,
        enrolments.account_id,
        enrolments.play_id,
        enrolments.play_version,
        enrolments.arm,
        enrolments.rollout_stage,
        enrolments.status,
        coalesce(enrolments.highest_tier, 'none') as highest_tier,
        enrolments.enrolled_on,
        enrolments.window_end,
        {{ as_of_date() }} >= enrolments.window_end as window_complete,
        coalesce(in_window.days_observed, 0) as days_observed,
        at_entry.segment,
        at_entry.edition,
        coalesce(at_entry.arr_at_entry, 0) as arr_at_entry,
        coalesce(in_window.best_closure >= 0.75, false) as setup_completed,
        coalesce(in_window.best_mau >= 0.9 * at_entry.mau_before_drop, false) as usage_recovered,
        (accounts.churned_at is null or accounts.churned_at > enrolments.window_end)
            as retained_30d,
        coalesce(in_window.had_valid_admin = 1, false) as valid_admin_restored,
        coalesce(expansions.expansions_won, 0) > 0 as expanded_30d,
        coalesce(docs.docs_published, 0) > 0 as docs_adopted,
        coalesce(advocacy.accepted, 0) > 0 and enrolments.play_id = 'advocacy_ask'
            as advocate_responded,
        coalesce(expansions.expansion_amount, 0) as expansion_amount
    from enrolments
    left join at_entry on enrolments.enrollment_id = at_entry.enrollment_id
    left join in_window on enrolments.enrollment_id = in_window.enrollment_id
    left join docs on enrolments.enrollment_id = docs.enrollment_id
    left join expansions on enrolments.enrollment_id = expansions.enrollment_id
    left join advocacy on enrolments.enrollment_id = advocacy.enrollment_id
    left join {{ ref('stg_accounts') }} as accounts
        on enrolments.account_id = accounts.account_id

)

select
    outcomes.*,
    -- revenue still under contract at the end of the window
    case when retained_30d then arr_at_entry else 0 end as retained_arr
from outcomes