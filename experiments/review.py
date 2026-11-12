"""The monthly operating review, written from the data.

Synthetic data, fictional company.

Run with:  uv run python run.py review     (after `experiments` and `evals`)

One page for the people who fund and staff the programme. It answers, in order:
what ran, what moved, what the agents did, what people had to pick up, whether the
data can be trusted, and which decisions are being asked for. Every number comes
from the warehouse, the operational store or the two reports; nothing is typed in.

The point of generating it: the review cannot drift from the system it describes,
and it costs nothing to produce every month.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pandas as pd

from common.config import load_yaml
from common.paths import DATA_DIR, ROOT
from common.store import open_store
from common.warehouse import open_warehouse
from engine.catalog import load_catalog

REVIEW_PATH = ROOT / "docs" / "operating-review.md"
EXPERIMENT_RESULTS = ROOT / "experiments" / "reports" / "experiment-results.json"
EVAL_RESULTS = ROOT / "evals" / "reports" / "eval-results.json"
LOOKBACK_DAYS = 30


def write_operating_review(data_dir: Path = DATA_DIR, path: Path = REVIEW_PATH) -> Path:
    """Gather the numbers and write the review. Returns the file written."""
    facts = gather(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(facts), encoding="utf-8", newline="\n")
    return path


# --- gathering -------------------------------------------------------------------------


def gather(data_dir: Path = DATA_DIR) -> dict:
    """Everything the review states, as plain numbers and small tables."""
    segments = load_yaml("rollout.yaml")["segments"]
    in_pilot = "coverage_tier IN (" + ", ".join(f"'{s}'" for s in segments) + ")"
    warehouse = open_warehouse(data_dir)
    today = pd.Timestamp(
        warehouse.query("SELECT max(snapshot_date) AS d FROM gold.account_current")["d"][0]
    ).date()
    before = today - timedelta(days=LOOKBACK_DAYS)

    def indicators(day) -> dict:
        row = warehouse.query(
            f"""
            SELECT count(*) AS accounts,
                   sum(arr) AS arr,
                   sum(mau_30d) AS monthly_active_users,
                   avg(prerequisite_closure_pct) AS setup_closure,
                   avg(seat_utilisation) AS seat_utilisation,
                   avg(health_score) AS health_score,
                   sum(CASE WHEN health_band = 'red' THEN 1 ELSE 0 END) AS red_accounts,
                   sum(assist_invocations_30d) AS assist_invocations
            FROM gold.account_daily
            WHERE {in_pilot} AND snapshot_date = DATE '{day.isoformat()}'
            """
        ).iloc[0]
        return {key: 0.0 if pd.isna(value) else float(value) for key, value in row.items()}

    quality = {
        "tests": warehouse.query(
            "SELECT count(*) AS total, sum(CASE WHEN status = 'pass' THEN 1 ELSE 0 END) AS passed "
            "FROM gold.dq_test_results"
        ).iloc[0],
        "contract": warehouse.query(
            "SELECT count(*) AS total, sum(CASE WHEN passed THEN 1 ELSE 0 END) AS passed "
            "FROM gold.dq_contract_checks"
        ).iloc[0],
        "rejected": int(warehouse.query("SELECT count(*) AS n FROM bronze.dead_letter")["n"][0]),
        "events": int(warehouse.query("SELECT count(*) AS n FROM silver.stg_events")["n"][0]),
    }
    handoffs = warehouse.query(
        """
        SELECT queue, sum(handoffs) AS handoffs, sum(open_now) AS open_now,
               sum(sla_breaches) AS sla_breaches, sum(converted) AS converted,
               sum(closed) AS closed, sum(unnecessary) AS unnecessary
        FROM gold.metrics_handoffs GROUP BY queue ORDER BY handoffs DESC
        """
    )
    now, then = indicators(today), indicators(before)
    warehouse.close()

    store = open_store(data_dir)
    since = before.isoformat()
    facts = {
        "as_of": today.isoformat(),
        "since": since,
        "segments": segments,
        "now": now,
        "then": then,
        "quality": quality,
        "handoffs": handoffs,
        "enrolments": pd.DataFrame(
            store.rows("SELECT play_id, arm, count(*) AS n FROM enrollments GROUP BY play_id, arm")
        ),
        "touches": pd.DataFrame(
            store.rows("SELECT tier, channel, count(*) AS n FROM touches GROUP BY tier, channel")
        ),
        "conversations": pd.DataFrame(
            store.rows("SELECT outcome, reason_code, answered_by, cost_usd FROM conversations")
        ),
        "feedback": pd.DataFrame(
            store.rows(
                "SELECT sentiment, theme, count(*) AS n FROM text_classifications "
                "GROUP BY sentiment, theme"
            )
        ),
        "mailbox": pd.DataFrame(
            store.rows("SELECT action, count(*) AS n FROM mailbox_triage GROUP BY action")
        ),
        "alerts": store.rows("SELECT * FROM queue_alerts ORDER BY alert_date"),
        "opt_outs": store.one(
            "SELECT count(*) AS n FROM consent_changes WHERE new_status = 'opted_out'"
        )["n"],
        "plays": {play.id: play for play in load_catalog().plays},
        "experiments": _read_json(EXPERIMENT_RESULTS),
        "evals": _read_json(EVAL_RESULTS),
    }
    return facts


def _read_json(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


# --- writing ---------------------------------------------------------------------------


def render(facts: dict) -> str:
    now, then = facts["now"], facts["then"]
    lines = [
        "# Operating review: Digital Success pilot",
        "",
        "Synthetic data, fictional company. Written by `uv run python run.py review` from the "
        "warehouse, the operational store and the two reports. Nothing here is typed by hand.",
        "",
        f"**Period:** {facts['since']} to {facts['as_of']} (simulated calendar). "
        f"**Segment:** {', '.join(facts['segments'])} accounts. "
        f"**In scope:** {now['accounts']:,.0f} accounts, ${now['arr'] / 1e6:.2f}M ARR.",
        "",
        "> This is a simulation. Customer reactions follow the assumptions in",
        "> `config/sim_effects.yaml`, so the lifts below are those assumptions measured back.",
        "> The review shows what a real one would contain and where each number comes from.",
        "",
        "## 1. The short version",
        "",
        *_headlines(facts),
        "",
        "## 2. Leading indicators in the segment",
        "",
        f"| Indicator | {LOOKBACK_DAYS} days ago | Now | Change |",
        "|---|---|---|---|",
        _row("Monthly active users (sum)", then, now, "monthly_active_users", "{:,.0f}"),
        _row("Setup steps completed (average)", then, now, "setup_closure", "{:.0%}", points=True),
        _row("Seat utilisation (average)", then, now, "seat_utilisation", "{:.0%}", points=True),
        _row("Health score (average)", then, now, "health_score", "{:.1f}"),
        _row("Accounts with red health", then, now, "red_accounts", "{:,.0f}"),
        _row("Assist invocations in 30 days", then, now, "assist_invocations", "{:,.0f}"),
        "",
        "These describe the whole segment, treated or not. They say where the segment is "
        "going. Only section 3 says what the plays changed.",
        "",
        "## 3. What the plays moved, against their holdouts",
        "",
        *_plays(facts),
        "",
        "## 4. What ran, by rung of the ladder",
        "",
        *_activity(facts),
        "",
        "## 5. The agents",
        "",
        *_agents(facts),
        "",
        "## 6. What people had to pick up",
        "",
        *_people(facts),
        "",
        "## 7. Can the data be trusted",
        "",
        *_quality(facts),
        "",
        "## 8. Decisions requested",
        "",
        *_decisions(facts),
        "",
    ]
    return "\n".join(lines)


def _headlines(facts: dict) -> list[str]:
    experiments = facts["experiments"]
    lines = []
    if experiments:
        working = [
            p["play_name"] for p in experiments["plays"] if p["verdict"].startswith("Working")
        ]
        early = [
            p["play_name"] for p in experiments["plays"] if p["verdict"].startswith("Too early")
        ]
        unproven = [
            p["play_name"] for p in experiments["plays"] if p["verdict"].startswith("No effect")
        ]
        lines.append(f"- **Working against a holdout:** {', '.join(working) or 'none yet'}.")
        lines.append(f"- **Not proven, keep testing:** {', '.join(unproven) or 'none'}.")
        lines.append(f"- **Too early to read:** {', '.join(early) or 'none'}.")
    conversations = facts["conversations"]
    if len(conversations):
        handed = (conversations["outcome"] == "escalated").mean()
        lines.append(
            f"- **Agent:** {len(conversations)} conversations, {handed:.0%} handed to a person."
        )
    handoffs = facts["handoffs"]
    if len(handoffs):
        breached = handoffs["sla_breaches"].sum() / max(handoffs["handoffs"].sum(), 1)
        lines.append(
            f"- **People:** {int(handoffs['handoffs'].sum())} tasks, {breached:.0%} past their SLA, "
            f"{int(handoffs['open_now'].sum())} open now."
        )
    quality = facts["quality"]
    lines.append(
        f"- **Data:** {int(quality['tests']['passed'])} of {int(quality['tests']['total'])} tests "
        f"and {int(quality['contract']['passed'])} of {int(quality['contract']['total'])} contract "
        "checks pass."
    )
    return lines


def _row(label: str, then: dict, now: dict, key: str, fmt: str, points: bool = False) -> str:
    change = now[key] - then[key]
    if points:
        shown = f"{change * 100:+.1f} points"
    else:
        shown = f"{change:+,.1f}" if abs(change) < 100 else f"{change:+,.0f}"
    return f"| {label} | {fmt.format(then[key])} | {fmt.format(now[key])} | {shown} |"


def _plays(facts: dict) -> list[str]:
    experiments = facts["experiments"]
    if not experiments:
        return ["No experiment report yet. Run `uv run python run.py experiments`."]
    lines = [
        "| Play | Stage | Success metric | Treatment | Holdout | Lift (95% interval) | Reading |",
        "|---|---|---|---|---|---|---|",
    ]
    for play in experiments["plays"]:
        treated = _rate(play, "treatment")
        held = _rate(play, "holdout")
        lift = (
            f"{play['lift']:+.0%} ({play['ci_low']:+.0%} to {play['ci_high']:+.0%})"
            if "lift" in play
            else "n/a"
        )
        reading = play["verdict"].split(":")[0].split(".")[0]
        lines.append(
            f"| {play['play_name']} | {play['rollout_stage']} | {play['metric']} | {treated} | "
            f"{held} | {lift} | {reading} |"
        )
    money = [p for p in experiments["plays"] if p["metric"] == "expanded_30d" and "lift" in p]
    for play in money:
        treated, held = play["money"]["treatment"], play["money"]["holdout"]
        lines += [
            "",
            f"**Expansion sourced by {play['play_name']}:** ${treated['expansion_won']:,.0f} closed "
            f"in treatment (${treated['expansion_per_account']:,.0f} per account) against "
            f"${held['expansion_won']:,.0f} in the holdout "
            f"(${held['expansion_per_account']:,.0f} per account).",
        ]
    lines += [
        "",
        "Full detail, cohorts and split checks: `experiments/reports/experiment-report.md`.",
    ]
    return lines


def _rate(play: dict, arm: str) -> str:
    n = play[f"n_{arm}"]
    return f"{play[f'successes_{arm}'] / n:.0%} of {n}" if n else "none"


def _activity(facts: dict) -> list[str]:
    enrolments, touches = facts["enrolments"], facts["touches"]
    if enrolments.empty:
        return ["Nothing has run yet."]
    treated = int(enrolments[enrolments["arm"] == "treatment"]["n"].sum())
    held = int(enrolments[enrolments["arm"] == "holdout"]["n"].sum())
    lines = [
        f"{treated} accounts entered a play and {held} were held out for comparison. "
        f"{facts['opt_outs']} contacts opted out and were removed the same day.",
        "",
        "| Rung | Channel | Touches delivered |",
        "|---|---|---|",
    ]
    for row in touches.sort_values(["tier", "channel"]).itertuples():
        lines.append(f"| {row.tier} | {row.channel} | {row.n} |")
    tasks = int(facts["handoffs"]["handoffs"].sum()) if len(facts["handoffs"]) else 0
    lines.append(f"| human | task for a person | {tasks} |")
    return lines


def _agents(facts: dict) -> list[str]:
    conversations, lines = facts["conversations"], []
    if conversations.empty:
        lines.append("No agent conversations yet.")
    else:
        escalated = conversations[conversations["outcome"] == "escalated"]
        writers = ", ".join(sorted(set(conversations["answered_by"].dropna()))) or "not recorded"
        lines += [
            f"- **Onboarding agent:** {len(conversations)} conversations (agent invocations), "
            f"{len(conversations) - len(escalated)} answered, {len(escalated)} handed off "
            f"({len(escalated) / len(conversations):.0%}). Model cost: "
            f"${conversations['cost_usd'].sum():.2f}.",
            f"- **Replies written by:** {writers}.",
        ]
        if len(escalated):
            reasons = escalated["reason_code"].value_counts()
            listed = ", ".join(f"{reason} ({count})" for reason, count in reasons.items())
            lines.append(f"- **Why it handed off:** {listed}.")
            gap = reasons.get("not_in_docs", 0)
            lines.append(
                f"- **Docs gap:** {gap} handoffs because no help article covered the question. "
                "Each one names an article to write."
            )
    mailbox = facts["mailbox"]
    if len(mailbox):
        listed = ", ".join(
            f"{row.action} ({row.n})"
            for row in mailbox.sort_values("n", ascending=False).itertuples()
        )
        lines.append(f"- **Mailbox triage:** {int(mailbox['n'].sum())} replies read. {listed}.")
    feedback = facts["feedback"]
    if len(feedback):
        negative = feedback[feedback["sentiment"] == "negative"].sort_values("n", ascending=False)
        themes = ", ".join(f"{row.theme} ({row.n})" for row in negative.head(4).itertuples())
        lines.append(
            f"- **Voice of the customer:** {int(feedback['n'].sum())} comments and tickets read; "
            f"{int(negative['n'].sum())} negative. What they are unhappy about: {themes or 'nothing'}."
        )
    evals = facts["evals"]
    if evals:
        scores = ", ".join(
            f"{suite} {counts['passed']} of {counts['run']}"
            for suite, counts in evals["totals"].items()
        )
        lines.append(f"- **Evaluation** (answers by: {evals['llm_mode']}): {scores}.")
    return lines


def _people(facts: dict) -> list[str]:
    handoffs = facts["handoffs"]
    if handoffs.empty:
        return ["No tasks yet."]
    lines = [
        "| Queue | Tasks | Open now | Past SLA | Closed with a good outcome | Unnecessary |",
        "|---|---|---|---|---|---|",
    ]
    for row in handoffs.itertuples():
        converted = f"{row.converted / row.closed:.0%}" if row.closed else "n/a"
        lines.append(
            f"| {row.queue} | {int(row.handoffs)} | {int(row.open_now)} | {int(row.sla_breaches)} | "
            f"{converted} | {int(row.unnecessary)} |"
        )
    closed = handoffs["closed"].sum()
    lines += [
        "",
        f"Escalation conversion (tasks closed as resolved, saved or an expansion opportunity): "
        f"{handoffs['converted'].sum() / closed:.0%}. "
        f'Unnecessary handoffs ("the agent should have handled this"): '
        f"{handoffs['unnecessary'].sum() / closed:.0%}; each becomes an evaluation case."
        if closed
        else "No task has been closed yet.",
    ]
    alerts = facts["alerts"]
    if alerts:
        queues = sorted({alert["queue"] for alert in alerts})
        lines.append(
            f"Capacity alerts: {len(alerts)} in the period, on {', '.join(queues)}. "
            f"Latest ({alerts[-1]['alert_date']}): {alerts[-1]['message']}"
        )
    else:
        lines.append("No capacity alerts in the period.")
    return lines


def _quality(facts: dict) -> list[str]:
    quality = facts["quality"]
    share = quality["rejected"] / max(quality["rejected"] + quality["events"], 1)
    return [
        f"- {int(quality['tests']['passed'])} of {int(quality['tests']['total'])} data tests pass. "
        f"{int(quality['contract']['passed'])} of {int(quality['contract']['total'])} checks on the "
        "contract of the production table pass.",
        f"- {quality['events']:,} product events were kept. {quality['rejected']:,} ({share:.1%}) "
        "were rejected at ingest and kept with a reason. The largest reason is a missing "
        "account id, which is an ask to Product Engineering (`docs/data-requirements.md`).",
    ]


def _decisions(facts: dict) -> list[str]:
    experiments = facts["experiments"]
    if not experiments:
        return ["None until the experiment report exists."]
    lines = ["| Play | Owner | Decision requested |", "|---|---|---|"]
    for play in experiments["plays"]:
        owner = facts["plays"][play["play_id"]].owner
        lines.append(f"| {play['play_name']} | {owner} | {play['recommendation']} |")
    lines += [
        "",
        "Each decision is a reviewed change to `config/plays.yaml` or `config/rollout.yaml` "
        "(`docs/change-control.md`). A play that scales keeps a 10% holdout.",
    ]
    return lines
