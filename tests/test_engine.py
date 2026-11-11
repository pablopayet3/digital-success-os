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
    assert len(catalog.plays) == 7
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
