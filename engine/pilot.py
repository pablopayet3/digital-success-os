"""Is the pilot ready, and what happened each week?

Synthetic data, fictional company. Two things the Pilot page shows:

  readiness_checks   The readiness checklist of docs/pilot-plan.md, answered from live
                     data instead of ticked by hand. One small function per line of
                     the checklist; each returns whether it holds and the evidence.
  weekly_notes       One row per week of the pilot: what ran, what people were asked to
                     do, and a note written by a rule about anything to look at.

Nothing here changes any data. It only reads the warehouse, the operational store, the
evaluation report and the configuration.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from common.config import load_yaml
from common.paths import DATA_DIR, ROOT
from common.store import Store, open_store
from common.warehouse import open_warehouse
from engine.consent import MAX_TOUCHES_PER_7_DAYS

EVAL_RESULTS = ROOT / "evals" / "reports" / "eval-results.json"
# Tables the dashboards read. If one is missing or empty, a page shows nothing.
DASHBOARD_TABLES = ["experiment_results", "metrics_play_summary", "metrics_handoffs"]


def readiness_checks(data_dir: Path = DATA_DIR, eval_results: Path = EVAL_RESULTS) -> list[dict]:
    """The checklist, answered now. Each item: check, passed (True or False), detail."""
    limits = load_yaml("rollout.yaml")["readiness"]
    queues = load_yaml("routing.yaml")["queues"]
    store = open_store(data_dir)
    warehouse = open_warehouse(data_dir)
    try:
        checks = [
            ("Data tests pass and the data is fresh", _data_is_tested_and_fresh(warehouse)),
            ("Consent and the frequency cap are enforced", _consent_and_cap_hold(store)),
            (
                "The agent passes its evaluation",
                _agent_passes_evals(eval_results, limits["min_eval_pass_rate"]),
            ),
            (
                "The human queues can take the work",
                _queues_have_capacity(store, queues, limits["max_backlog_days"]),
            ),
            ("Handoffs come back with a return signal", _return_signal_works(store)),
            ("The results tables are built and current", _results_are_current(warehouse)),
        ]
    finally:
        warehouse.close()
    return [
        {"check": name, "passed": passed, "detail": detail} for name, (passed, detail) in checks
    ]


def _data_is_tested_and_fresh(warehouse) -> tuple[bool, str]:
    tests = warehouse.query(
        "SELECT count(*) AS total, sum(CASE WHEN status = 'pass' THEN 1 ELSE 0 END) AS passed "
        "FROM gold.dq_test_results"
    ).iloc[0]
    contract = warehouse.query(
        "SELECT count(*) AS total, sum(CASE WHEN passed THEN 1 ELSE 0 END) AS passed "
        "FROM gold.dq_contract_checks"
    ).iloc[0]
    stale = warehouse.query("SELECT count(*) AS n FROM gold.dq_freshness WHERE status <> 'pass'")
    fresh = int(stale["n"][0]) == 0
    detail = (
        f"{int(tests['passed'])} of {int(tests['total'])} data tests pass; "
        f"{int(contract['passed'])} of {int(contract['total'])} contract checks pass; "
        f"sources are {'fresh' if fresh else 'STALE'}."
    )
    all_pass = tests["passed"] == tests["total"] and contract["passed"] == contract["total"]
    return bool(all_pass and tests["total"] > 0 and fresh), detail


def _consent_and_cap_hold(store: Store) -> tuple[bool, str]:
    """Look for the two things that must never happen, in what was actually sent."""
    touches = store.rows(
        "SELECT contact_id, touch_date, channel FROM touches WHERE contact_id IS NOT NULL"
    )
    busiest = most_touches_in_7_days(touches)
    opt_outs = {
        row["contact_id"]: row["changed_on"]
        for row in store.rows("SELECT contact_id, changed_on FROM consent_changes")
    }
    # An email dated after the contact opted out would be a consent failure.
    emails_after_opt_out = sum(
        1
        for touch in touches
        if touch["channel"] == "email"
        and touch["contact_id"] in opt_outs
        and touch["touch_date"] > opt_outs[touch["contact_id"]]
    )
    kept_out = store.one(
        "SELECT count(*) AS n FROM audit_log WHERE reason LIKE '%allowed to email%'"
    )["n"]
    detail = (
        f"Most touches any contact received in 7 days: {busiest} (cap {MAX_TOUCHES_PER_7_DAYS}). "
        f"Emails sent after an opt-out: {emails_after_opt_out} ({len(opt_outs)} opt-outs). "
        f"Kept out of a play because nobody could be emailed: {kept_out} decisions."
    )
    return busiest <= MAX_TOUCHES_PER_7_DAYS and emails_after_opt_out == 0, detail


def most_touches_in_7_days(touches: list[dict]) -> int:
    """The largest number of touches one contact received inside any seven days."""
    days_by_contact: dict[str, list[date]] = {}
    for touch in touches:
        day = date.fromisoformat(str(touch["touch_date"])[:10])
        days_by_contact.setdefault(touch["contact_id"], []).append(day)
    busiest = 0
    for days in days_by_contact.values():
        days.sort()
        for index, start in enumerate(days):
            in_window = sum(1 for day in days[index:] if day < start + timedelta(days=7))
            busiest = max(busiest, in_window)
    return busiest


def _agent_passes_evals(results_file: Path, minimum: float) -> tuple[bool, str]:
    if not results_file.exists():
        return False, "No evaluation report yet. Run: uv run python run.py evals"
    results = json.loads(results_file.read_text(encoding="utf-8"))
    version = results["prompt_in_use"]
    totals = results["totals"][f"onboarding agent ({version})"]
    if not totals["run"]:
        return False, "The evaluation ran no agent cases."
    rate = totals["passed"] / totals["run"]
    detail = (
        f"Onboarding agent, prompt {version}: {totals['passed']} of {totals['run']} cases pass "
        f"({rate:.0%}; the bar is {minimum:.0%}). Answers produced by: {results['llm_mode']}."
    )
    return rate >= minimum, detail


def _queues_have_capacity(store: Store, queues: dict, max_days: float) -> tuple[bool, str]:
    """A queue is in trouble when its open tasks are more than a few days of its capacity."""
    open_now = Counter(
        row["queue"] for row in store.rows("SELECT queue FROM ctas WHERE status <> 'resolved'")
    )
    over = [
        f"{queues[queue]['name']} ({count} open, {queues[queue]['capacity_per_day']} a day)"
        for queue, count in open_now.items()
        if queue in queues and count > max_days * queues[queue]["capacity_per_day"]
    ]
    last_alert = store.one("SELECT max(alert_date) AS day FROM queue_alerts")["day"]
    detail = (
        f"{sum(open_now.values())} tasks open across {len(queues)} queues. "
        + (f"Over {max_days:g} days of capacity: {'; '.join(over)}. " if over else "")
        + (f"Last capacity alert: {last_alert}." if last_alert else "No capacity alert so far.")
    )
    return not over, detail


def _return_signal_works(store: Store) -> tuple[bool, str]:
    """Every task a person closed must say what happened and what the journey does next."""
    closed = store.one("SELECT count(*) AS n FROM ctas WHERE status = 'resolved'")["n"]
    complete = store.one(
        "SELECT count(*) AS n FROM ctas WHERE status = 'resolved' "
        "AND outcome IS NOT NULL AND next_state IS NOT NULL"
    )["n"]
    returned = store.one(
        "SELECT count(*) AS n FROM journey_events WHERE event = 'return_signal'"
    )["n"]
    detail = (
        f"{complete} of {closed} closed tasks carry an outcome and the journey's next step; "
        f"{returned} journeys received a return signal."
    )
    return closed > 0 and complete == closed, detail


def _results_are_current(warehouse) -> tuple[bool, str]:
    today = str(warehouse.query("SELECT max(snapshot_date) AS d FROM gold.account_current")["d"][0])
    try:
        counts = {
            table: int(warehouse.query(f"SELECT count(*) AS n FROM gold.{table}")["n"][0])
            for table in DASHBOARD_TABLES
        }
        as_of = str(warehouse.query("SELECT max(as_of) AS d FROM gold.experiment_results")["d"][0])
    except Exception:  # a table that does not exist yet
        return False, "Results are not built yet. Run: uv run python run.py experiments"
    empty = [table for table, rows in counts.items() if rows == 0]
    current = as_of[:10] == today[:10]
    detail = (
        f"Results as of {as_of[:10]}; the data is as of {today[:10]}. "
        + (f"Empty: {', '.join(empty)}." if empty else "Every results table has rows.")
    )
    return current and not empty, detail


def weekly_notes(data_dir: Path = DATA_DIR) -> list[dict]:
    """One row per week of the pilot, oldest first, with a note about what to look at."""
    store = open_store(data_dir)
    weeks: dict[str, Counter] = {}

    def count(day, what: str, amount: int = 1) -> None:
        if day:
            weeks.setdefault(_week_of(day), Counter())[what] += amount

    for row in store.rows("SELECT enrolled_on, arm FROM enrollments"):
        count(row["enrolled_on"], "entered" if row["arm"] == "treatment" else "held_out")
    for row in store.rows("SELECT touch_date FROM touches"):
        count(row["touch_date"], "touches")
    for row in store.rows("SELECT day FROM conversations"):
        count(row["day"], "agent_conversations")
    for row in store.rows("SELECT created_on, resolved_on, picked_up_on, sla_due_on FROM ctas"):
        count(row["created_on"], "handed_to_people")
        count(row["resolved_on"], "closed_by_people")
        if row["picked_up_on"] and row["picked_up_on"] > row["sla_due_on"]:
            count(row["picked_up_on"], "picked_up_late")
    for row in store.rows("SELECT changed_on FROM consent_changes"):
        count(row["changed_on"], "opt_outs")
    for row in store.rows("SELECT DISTINCT alert_date FROM queue_alerts"):
        count(row["alert_date"], "days_with_a_queue_alert")

    columns = [
        "entered", "held_out", "touches", "agent_conversations", "handed_to_people",
        "closed_by_people", "picked_up_late", "opt_outs", "days_with_a_queue_alert",
    ]  # fmt: skip
    return [
        {
            "week_starting": week,
            **{column: weeks[week][column] for column in columns},
            "note": _note(weeks[week]),
        }
        for week in sorted(weeks)
    ]


def _week_of(day) -> str:
    """The Monday of the week a date falls in, as text."""
    day = date.fromisoformat(str(day)[:10])
    return (day - timedelta(days=day.weekday())).isoformat()


def _note(week: Counter) -> str:
    """What a reviewer should look at this week. Rules, so the same data gives the same note."""
    notes = []
    alert_days = week["days_with_a_queue_alert"]
    if alert_days:
        days = "1 day" if alert_days == 1 else f"{alert_days} days"
        notes.append(
            f"A queue was over its daily capacity on {days}: tasks were worked by priority, "
            "then by SLA date."
        )
    if week["handed_to_people"] and week["picked_up_late"] > 0.2 * week["handed_to_people"]:
        notes.append(f"{week['picked_up_late']} tasks were picked up after their SLA date.")
    if week["opt_outs"]:
        notes.append(f"{week['opt_outs']} contacts opted out and were removed the same day.")
    if week["entered"] and not week["touches"] and not week["handed_to_people"]:
        notes.append("Accounts entered plays but nothing was delivered: check the journeys.")
    return " ".join(notes) or "Nothing to flag."
