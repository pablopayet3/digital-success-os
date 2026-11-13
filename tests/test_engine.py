"""Tests for the rules engine, journeys, consent, handoffs and the daily loop (Phase 4).

Synthetic data, fictional company. Most tests look at what the engine did during
six simulated days on the small world.
"""

import json
from datetime import date

import duckdb
import pytest

from common.store import Store
from engine import journeys, rules
from engine.assignment import assign_arm, in_rollout
from engine.catalog import Catalog, find_problems, load_catalog
from engine.context import load_day
from engine.handoff import HandoffPacket, check_queue_capacity, create_cta, resolve_cta
from ingest.load import warehouse_path

OPEN = ("active", "waiting_on_human", "holdout")


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    return load_catalog()


# --- The catalog ---------------------------------------------------------------------


def test_every_play_declares_its_ladder_rollout_and_holdout(catalog):
    assert len(catalog.plays) == 8
    for play in catalog.plays:
        assert play.intervention_ladder, play.id
        assert play.rollout_stage in ("slice", "full")
        assert 0 <= play.holdout_pct <= 1
        assert play.success_metric["id"]
        assert play.owner


def test_a_broken_catalog_is_refused(catalog):
    broken = catalog.model_copy(deep=True)
    broken.plays[0].journey = "journey_that_does_not_exist"
    broken.plays[1].trigger = ["not_a_signal"]
    problems = find_problems(broken)
    assert any("does not exist" in problem for problem in problems)
    assert any("unknown trigger signal" in problem for problem in problems)


# --- Holdout and rollout ---------------------------------------------------------------


def test_assignment_never_changes_and_is_balanced(catalog):
    play = catalog.play("onboarding_rescue")
    accounts = [f"A{n:04d}" for n in range(1, 3001)]
    arms = [assign_arm(account, play) for account in accounts]
    assert arms == [assign_arm(account, play) for account in accounts]  # same every time
    assert 0.46 < arms.count("holdout") / len(arms) < 0.54  # close to the 50% asked for

    slice_play = catalog.play("edition_upgrade")
    assert slice_play.rollout_stage == "slice"
    share = sum(in_rollout(account, slice_play) for account in accounts) / len(accounts)
    assert 0.07 < share < 0.13  # close to 10%


def test_a_new_version_reshuffles_the_groups(catalog):
    play = catalog.play("onboarding_rescue")
    next_version = play.model_copy(update={"version": play.version + 1})
    accounts = [f"A{n:04d}" for n in range(1, 501)]
    moved = sum(assign_arm(a, play) != assign_arm(a, next_version) for a in accounts)
    assert moved > 150


# --- What the rules engine decided ---------------------------------------------------------


def test_the_simulation_ran_and_enrolled_accounts(simulated, ops):
    summaries, _ = simulated
    assert len(summaries) == 6
    assert sum(day["entered"] for day in summaries) > 20
    assert sum(day["holdout"] for day in summaries) > 5
    plays = {row["play_id"] for row in ops.rows("SELECT DISTINCT play_id FROM enrollments")}
    assert {"onboarding_rescue", "expansion_seats", "find_the_admin"} <= plays


def test_every_decision_is_in_the_audit_log_with_a_reason(ops):
    enrolled = ops.one("SELECT count(*) AS n FROM enrollments")["n"]
    logged = ops.one(
        "SELECT count(*) AS n FROM audit_log WHERE decision IN ('entered', 'holdout')"
    )["n"]
    assert logged == enrolled
    without_reason = ops.one(
        "SELECT count(*) AS n FROM audit_log WHERE reason IS NULL OR reason = ''"
    )["n"]
    assert without_reason == 0
    assert ops.one("SELECT count(*) AS n FROM audit_log WHERE decision = 'excluded'")["n"] > 0


def test_only_the_pilot_segment_is_enrolled(simulated, ops):
    _, data_dir = simulated
    con = duckdb.connect(str(warehouse_path(data_dir)))
    tiers = dict(con.execute("SELECT account_id, coverage_tier FROM gold.dim_account").fetchall())
    con.close()
    enrolled = {row["account_id"] for row in ops.rows("SELECT account_id FROM enrollments")}
    assert {tiers[account] for account in enrolled} == {"uncovered"}


def test_an_account_is_in_one_exclusive_play_at_a_time(ops, catalog):
    exclusive = [play.id for play in catalog.plays if play.exclusive]
    open_now: dict[str, int] = {}
    for row in ops.rows("SELECT account_id, play_id, status FROM enrollments"):
        if row["status"] in OPEN and row["play_id"] in exclusive:
            open_now[row["account_id"]] = open_now.get(row["account_id"], 0) + 1
    assert open_now and max(open_now.values()) == 1


def test_holdout_accounts_are_never_touched(ops):
    touched = ops.one(
        """
        SELECT count(*) AS n FROM touches
        INNER JOIN enrollments ON touches.enrollment_id = enrollments.enrollment_id
        WHERE enrollments.arm = 'holdout'
        """
    )["n"]
    holdout_ctas = ops.one(
        """
        SELECT count(*) AS n FROM ctas
        INNER JOIN enrollments ON ctas.enrollment_id = enrollments.enrollment_id
        WHERE enrollments.arm = 'holdout'
        """
    )["n"]
    assert touched == 0 and holdout_ctas == 0
    assert ops.one("SELECT count(*) AS n FROM enrollments WHERE arm = 'holdout'")["n"] > 0


# --- Consent and frequency -----------------------------------------------------------------


def test_emails_only_go_to_contacts_who_opted_in(simulated, ops):
    _, data_dir = simulated
    con = duckdb.connect(str(warehouse_path(data_dir)))
    emailable = {row[0] for row in con.execute(
        "SELECT contact_id FROM gold.dim_contact WHERE can_email"
    ).fetchall()}  # fmt: skip
    # someone who used the unsubscribe link after our email was allowed at the time
    unsubscribed_later = {row[0] for row in con.execute(
        "SELECT contact_id FROM silver.stg_email_engagement WHERE unsubscribed"
    ).fetchall()}  # fmt: skip
    con.close()
    email_touches = ops.rows("SELECT contact_id FROM touches WHERE channel = 'email'")
    emailed = {row["contact_id"] for row in email_touches}
    assert emailed
    assert emailed <= emailable | unsubscribed_later


def test_nobody_gets_more_than_two_touches_in_seven_days(ops):
    by_contact: dict[str, list[date]] = {}
    for row in ops.rows("SELECT contact_id, touch_date FROM touches WHERE contact_id IS NOT NULL"):
        by_contact.setdefault(row["contact_id"], []).append(date.fromisoformat(row["touch_date"]))
    for days in by_contact.values():
        days.sort()
        for first, third in zip(days, days[2:], strict=False):
            assert (third - first).days >= 7  # a third touch needs a new seven-day window


def test_paused_accounts_get_no_email(ops):
    emails_while_paused = ops.one(
        """
        SELECT count(*) AS n FROM touches
        INNER JOIN paused_accounts ON touches.account_id = paused_accounts.account_id
        WHERE touches.channel = 'email' AND touches.touch_date >= paused_accounts.paused_on
        """
    )["n"]
    assert emails_while_paused == 0


# --- Handoffs and the return signal ----------------------------------------------------------


def test_a_handoff_packet_has_everything_a_human_needs(ops):
    ctas = ops.rows("SELECT * FROM ctas")
    assert ctas
    for cta in ctas:
        packet = HandoffPacket.model_validate_json(cta["packet"])
        assert packet.account_name and packet.recommended_next_step
        assert packet.queue == cta["queue"] and packet.sla_due_at >= packet.created_at
        assert packet.account_snapshot["health"]["score"] is not None
        assert packet.trigger["source"] in ("journey", "agent", "mailbox")
    sales = [json.loads(c["packet"]) for c in ctas if c["queue"] == "sales"]
    assert sales and all(packet["brief"] for packet in sales)  # Sales always gets a brief


def test_the_return_signal_moves_the_journey_on(simulated, catalog, tmp_path):
    """Run the engine once on a fresh store, then resolve its CTAs in different ways."""
    _, data_dir = simulated
    store = Store(f"sqlite:///{(tmp_path / 'return_signal.db').as_posix()}")
    ctx = load_day(data_dir, store, catalog)
    rules.evaluate_plays(ctx)
    journeys.advance_journeys(ctx)
    today = ctx.today

    waiting = store.rows(
        """
        SELECT ctas.cta_id, ctas.step_id, enrollments.enrollment_id, enrollments.play_id
        FROM ctas INNER JOIN enrollments ON ctas.enrollment_id = enrollments.enrollment_id
        WHERE ctas.status = 'open' AND enrollments.status = 'waiting_on_human'
        ORDER BY ctas.cta_id
        """
    )
    assert len(waiting) >= 3

    def enrollment(enrollment_id: str) -> dict:
        return store.one("SELECT * FROM enrollments WHERE enrollment_id = :id", id=enrollment_id)

    # "Not a fit": the account leaves the journey.
    first = waiting[0]
    result = resolve_cta(store, catalog, first["cta_id"], "not_a_fit", today, notes="No need.")
    assert result["next_state"] == "exit"
    assert enrollment(first["enrollment_id"])["status"] == "exited"

    # Resolving twice is refused, and so is an outcome that is not in the list.
    with pytest.raises(ValueError, match="already resolved"):
        resolve_cta(store, catalog, first["cta_id"], "resolved", today)
    with pytest.raises(ValueError, match="Unknown outcome"):
        resolve_cta(store, catalog, waiting[1]["cta_id"], "made_up_outcome", today)

    # "The agent should have handled this" feeds the evaluation queue: the feedback loop.
    second = waiting[1]
    resolve_cta(store, catalog, second["cta_id"], "agent_should_have_handled", today, notes="Easy.")
    candidate = store.one("SELECT * FROM eval_candidates WHERE cta_id = :id", id=second["cta_id"])
    assert candidate is not None and candidate["human_notes"] == "Easy."

    # A handoff in the middle of a journey: once resolved, the journey resumes at the
    # step after the one that handed off.
    stalled = store.one(
        "SELECT * FROM enrollments WHERE play_id = 'onboarding_rescue' AND status = 'active'"
    )
    assert stalled is not None
    cta_id = create_cta(
        ctx, stalled["account_id"], "pooled_csm", "normal", "customer_asked_for_person",
        "Customer asked for a person", "Call them.", source="agent",
        enrollment=stalled, step_id="agent_help",
    )  # fmt: skip
    store.update(
        "enrollments", {"enrollment_id": stalled["enrollment_id"]}, status="waiting_on_human"
    )
    result = resolve_cta(store, catalog, cta_id, "resolved", today)
    resumed = enrollment(stalled["enrollment_id"])
    assert result["next_state"] == "re_enter_journey"
    assert resumed["status"] == "active" and resumed["current_step"] == "wait_after_agent"
    assert resumed["next_action_on"] > ctx.day


def test_staff_never_work_more_than_their_daily_capacity(ops, catalog):
    for queue, settings in catalog.routing["queues"].items():
        busiest = ops.one(
            """
            SELECT max(n) AS n FROM (
                SELECT count(*) AS n FROM ctas
                WHERE queue = :queue AND resolved_by = 'simulated staff' GROUP BY resolved_on
            ) AS per_day
            """,
            queue=queue,
        )["n"]
        assert (busiest or 0) <= settings["capacity_per_day"]


def test_an_alert_fires_when_a_queue_holds_more_than_its_team_can_work(
    simulated, catalog, tmp_path
):
    _, data_dir = simulated
    tiny_team = catalog.model_copy(deep=True)
    for settings in tiny_team.routing["queues"].values():
        settings["capacity_per_day"] = 1
    store = Store(f"sqlite:///{(tmp_path / 'alerts.db').as_posix()}")
    ctx = load_day(data_dir, store, tiny_team)
    rules.evaluate_plays(ctx)
    journeys.advance_journeys(ctx)

    alerts = check_queue_capacity(ctx)
    assert alerts
    assert all(alert["open_ctas"] > 2 * alert["capacity_per_day"] for alert in alerts)
    assert store.one("SELECT count(*) AS n FROM queue_alerts")["n"] == len(alerts)


# --- The closed loop ---------------------------------------------------------------------------


def test_customers_react_to_touches_and_the_pipeline_sees_it(simulated, current_world):
    _, data_dir = simulated
    assert current_world.interventions_log  # the world received the engine's touches
    con = duckdb.connect(str(warehouse_path(data_dir)))
    journey_emails, opened = con.execute(
        """
        SELECT count(*), count(opened_at) FROM silver.stg_email_engagement
        WHERE campaign LIKE 'play_%'
        """
    ).fetchone()
    con.close()
    assert journey_emails > 0 and opened > 0  # journey emails flow back through the pipeline


def test_operational_tables_are_copied_into_the_warehouse(simulated, ops):
    _, data_dir = simulated
    con = duckdb.connect(str(warehouse_path(data_dir)))
    in_warehouse = con.execute("SELECT count(*) FROM bronze.ops_enrollments").fetchone()[0]
    con.close()
    # the copy was taken by the closing pipeline run, before these tests changed anything
    assert in_warehouse == ops.one("SELECT count(*) AS n FROM enrollments")["n"]


def test_adding_a_segment_scales_the_same_plays_to_it(simulated, tmp_path):
    """Scale the pattern: one config value extends the plays to the pooled segment."""
    _, data_dir = simulated

    def enrolled_tiers(segments: list[str], name: str) -> set[str]:
        store = Store(f"sqlite:///{(tmp_path / name).as_posix()}")
        ctx = load_day(data_dir, store)
        ctx.segments = segments
        rules.evaluate_plays(ctx)
        accounts = {row["account_id"] for row in store.rows("SELECT account_id FROM enrollments")}
        return {ctx.accounts[account]["coverage_tier"] for account in accounts}

    assert enrolled_tiers(["uncovered"], "pilot.db") == {"uncovered"}
    assert enrolled_tiers(["uncovered", "pooled"], "scaled.db") == {"uncovered", "pooled"}


# --- Pilot readiness, weekly notes, journey funnel --------------------------------------------


def test_the_readiness_checklist_is_answered_from_live_data(simulated, tmp_path):
    from engine.pilot import readiness_checks

    _, data_dir = simulated
    checks = {check["check"]: check for check in readiness_checks(data_dir)}
    assert len(checks) == 6 and all(check["detail"] for check in checks.values())
    # What the engine promises must hold in what it actually sent.
    assert checks["Consent and the frequency cap are enforced"]["passed"]
    assert checks["Data tests pass and the data is fresh"]["passed"]

    # An agent that fails too many cases makes the pilot "not ready".
    failing = tmp_path / "eval-results.json"
    totals = {"onboarding agent (v3)": {"run": 30, "passed": 20}}
    failing.write_text(
        json.dumps({"prompt_in_use": "v3", "totals": totals, "llm_mode": "test"}), encoding="utf-8"
    )
    agent = readiness_checks(data_dir, failing)[2]
    assert agent["check"] == "The agent passes its evaluation" and not agent["passed"]
    assert "20 of 30" in agent["detail"]


def test_the_frequency_cap_check_counts_inside_any_seven_days():
    from engine.pilot import most_touches_in_7_days

    def touch(contact, day):
        return {"contact_id": contact, "touch_date": day}

    spread_out = [touch("C1", "2026-01-01"), touch("C1", "2026-01-08"), touch("C1", "2026-01-15")]
    assert most_touches_in_7_days(spread_out) == 1
    bunched = [touch("C1", "2026-01-01"), touch("C1", "2026-01-05"), touch("C1", "2026-01-07")]
    assert most_touches_in_7_days(bunched + [touch("C2", "2026-01-01")]) == 3
    assert most_touches_in_7_days([]) == 0


def test_weekly_notes_have_one_row_per_week_and_add_up(simulated, ops):
    from engine.pilot import weekly_notes

    _, data_dir = simulated
    weeks = weekly_notes(data_dir)
    starts = [week["week_starting"] for week in weeks]
    assert starts == sorted(set(starts)) and all(week["note"] for week in weeks)
    assert all(date.fromisoformat(start).weekday() == 0 for start in starts)  # Mondays
    entered = ops.one("SELECT count(*) AS n FROM enrollments WHERE arm = 'treatment'")["n"]
    assert sum(week["entered"] for week in weeks) == entered
    assert sum(week["handed_to_people"] for week in weeks) == len(ops.rows("SELECT 1 FROM ctas"))


def test_the_journey_funnel_follows_the_journey_definition(simulated, ops):
    from engine.journeys import journey_funnel

    catalog = load_catalog()
    play = next(play for play in catalog.plays if play.id == "onboarding_rescue")
    funnel = journey_funnel(ops, catalog.journeys[play.journey], play.id)
    stages = [row["stage"] for row in funnel]
    assert stages[0] == "Signal fired and eligible" and stages[-1] == "Journey completed"
    assert stages[2:-1] == [
        "email: setup_guide (digital)", "agent: agent_help (agentic)", "cta: csm_handoff (human)",
    ]  # fmt: skip
    eligible, entered = funnel[0]["accounts"], funnel[1]["accounts"]
    assert eligible >= entered > 0
    assert all(row["accounts"] <= entered for row in funnel[2:])


def test_the_scaling_preview_decides_like_the_engine_and_writes_nothing(simulated, ops):
    """Adding a segment is previewed with the engine's own rules, without touching the store."""
    from engine.rules import preview_segment

    _, data_dir = simulated
    before = (len(ops.rows("SELECT 1 FROM enrollments")), len(ops.rows("SELECT 1 FROM audit_log")))
    ctx = load_day(data_dir, ops, load_catalog())
    rows = {row["play_id"]: row for row in preview_segment(ctx, "pooled")}
    after = (len(ops.rows("SELECT 1 FROM enrollments")), len(ops.rows("SELECT 1 FROM audit_log")))
    assert before == after, "a preview must not enrol anyone or write to the audit log"
    assert set(rows) == {play.id for play in load_catalog().plays}

    eligible = sum(row["would_enter"] + row["would_be_held_out"] for row in rows.values())
    pooled = sum(1 for account in ctx.accounts.values() if account["coverage_tier"] == "pooled")
    assert 0 < eligible <= pooled * len(rows)
    # A play with no holdout holds nobody out; a play that starts with a task names its queue.
    assert rows["find_the_admin"]["would_be_held_out"] == 0
    assert rows["find_the_admin"]["first_day_queue"] == "admin_research"
    assert rows["onboarding_rescue"]["first_day_queue"] is None  # it starts with an email
    # A tier with no accounts gives zeros, not an error.
    assert all(row["would_enter"] == 0 for row in preview_segment(ctx, "no_such_tier"))


# --- Drafts that wait for a person's approval (ADR 0029) ---------------------------------


def test_a_draft_waits_for_approval_and_nothing_is_sent_before(simulated, catalog, tmp_path):
    from engine import approvals, consent

    _, data_dir = simulated
    store = Store(f"sqlite:///{(tmp_path / 'approvals.db').as_posix()}")
    ctx = load_day(data_dir, store, catalog)
    # Two customers we may email, put straight into the reference request play.
    chosen = []
    for account_id in sorted(ctx.accounts):
        contact = consent.best_contact(ctx, account_id)
        if contact and consent.can_email(ctx, contact) and account_id not in ctx.paused:
            chosen.append((account_id, contact))
        if len(chosen) == 2:
            break
    for number, (account_id, contact) in enumerate(chosen):
        store.insert(
            "enrollments",
            {"enrollment_id": f"E-TEST-{number}", "account_id": account_id,
             "play_id": "advocacy_ask", "play_version": 1, "arm": "treatment",
             "rollout_stage": "slice", "status": "active", "trigger_signal": "advocate_ready",
             "trigger_evidence": "NPS score of 10", "contact_id": contact["contact_id"],
             "current_step": "reference_request", "next_action_on": ctx.day,
             "enrolled_on": ctx.day},
        )  # fmt: skip
    counts = journeys.advance_journeys(ctx)

    # The request is written as a draft for the success managers' queue. Nothing is sent.
    drafts = store.rows("SELECT * FROM drafts ORDER BY enrollment_id")
    assert counts["drafts"] == 2 and [d["status"] for d in drafts] == ["pending", "pending"]
    assert all(d["queue"] == "pooled_csm" and d["subject"] and d["body"] for d in drafts)
    assert store.rows("SELECT * FROM touches WHERE play_id = 'advocacy_ask'") == []

    def status(enrollment_id: str) -> str:
        row = store.one(
            "SELECT status FROM enrollments WHERE enrollment_id = :id", id=enrollment_id
        )
        return row["status"]

    assert status("E-TEST-0") == status("E-TEST-1") == "waiting_on_human"

    # Approved: the journey resumes and the next run sends the email, once.
    approvals.decide(store, drafts[0]["draft_id"], True, ctx.day, "CSM", "Good moment.")
    assert status("E-TEST-0") == "active"
    journeys.advance_journeys(ctx)
    sent = store.rows("SELECT * FROM touches WHERE enrollment_id = 'E-TEST-0'")
    assert len(sent) == 1 and sent[0]["channel"] == "email"
    assert (
        store.one("SELECT status FROM drafts WHERE enrollment_id = 'E-TEST-0'")["status"] == "sent"
    )

    # Rejected: the play ends for that customer, and nothing is ever sent.
    approvals.decide(store, drafts[1]["draft_id"], False, ctx.day, "CSM", "Not now.")
    assert status("E-TEST-1") == "exited"
    assert store.rows("SELECT * FROM touches WHERE enrollment_id = 'E-TEST-1'") == []
    with pytest.raises(ValueError, match="not waiting"):
        approvals.decide(store, drafts[1]["draft_id"], True, ctx.day, "CSM")


def test_only_an_email_can_wait_for_approval_and_only_for_a_real_queue(catalog):
    broken = catalog.model_copy(deep=True)
    steps = broken.journeys["advocacy_ask"].steps
    steps[0].approval = "no_such_queue"
    steps[1].approval = "pooled_csm"  # a wait step
    problems = find_problems(broken)
    assert any("unknown approval queue" in problem for problem in problems)
    assert any("only an email can wait for approval" in problem for problem in problems)


def test_the_reference_request_is_only_for_customers_who_earned_it(simulated):
    """The signal's rule, checked against the warehouse: every customer it names is a
    recent promoter, green, settled, with no open urgent ticket and no churn flag."""
    _, data_dir = simulated
    with duckdb.connect(str(warehouse_path(data_dir))) as con:
        wrong = con.execute(
            """
            SELECT count(*) FROM gold.signals AS s
            JOIN gold.account_daily AS a
              ON s.account_id = a.account_id AND s.snapshot_date = a.snapshot_date
            WHERE s.signal_id = 'advocate_ready'
              AND NOT (a.latest_nps_score >= 9 AND a.health_band = 'green'
                       AND a.account_age_days >= 90 AND NOT a.churn_risk_high
                       AND coalesce(a.open_high_priority_tickets, 0) = 0
                       AND a.latest_nps_date >= a.snapshot_date - INTERVAL 90 DAY)
            """
        ).fetchone()[0]
    assert wrong == 0


def test_the_event_log_says_what_happened_in_plain_words(ops):
    from app import events

    recent = events.latest_events(ops, limit=20)
    assert recent, "six simulated days should leave a record"
    assert [r["day"] for r in recent] == sorted((r["day"] for r in recent), reverse=True)
    line = events.sentence(recent[0], "Wexyx Energy", "Setup has stalled", "Onboarding rescue")
    assert line.startswith("Wexyx Energy ") and line.endswith("in the play Onboarding rescue.")
    assert "->" not in line and "_" not in line.split("Why")[0]
