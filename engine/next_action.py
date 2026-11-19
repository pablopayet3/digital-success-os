"""The next best action for one customer: what should happen next, who does it, and why.

Synthetic data, fictional company. The engine already decides, play by play, who enters,
who is held out and who is kept out. A person looking at one customer needs the answer
the other way round: across every play, what is the one thing to do now? (ADR 0033)

The rule is an order of precedence, from what is already in motion to what is not:

  1. A task is waiting for a person      -> that person acts (the most urgent first).
  2. A draft is waiting for approval     -> a success manager decides.
  3. A play is under way                 -> let it run; its next step and date.
  4. The customer is held out            -> leave it alone until the comparison ends.
  5. A signal is firing                  -> the play it starts, or why the engine kept
                                            the customer out and what would unblock it.
  6. Nothing is firing                   -> no action; the reason is said.

The first that applies is the recommendation. The others that also apply are listed
after it, so nothing the system knows is hidden. Nothing here writes anything.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

# Exclusions a person can do something about, and what that is.
UNBLOCK = {
    "no admin we are allowed to email": "Find an admin who may be emailed.",
    "no contact we are allowed to email": "Find a contact who may be emailed.",
    "an escalation is open with a human": "Close the open task first; the play can start after.",
}


def next_best_action(
    store, catalog, account_id: str, firing: dict[str, str], account: dict | None = None
) -> dict:
    """Return {"action", "who", "why", "also"} for one customer. `firing`: signal -> evidence.

    `account` (today's row of gold.account_current) lets a red health score be noticed
    even when no rule has fired.
    """
    queues = catalog.routing["queues"]
    candidates = (
        _open_tasks(store, account_id, queues)
        + _drafts(store, account_id, catalog, queues)
        + _plays_in_motion(store, account_id, catalog)
        + _signals(store, account_id, catalog, firing)
    )
    if not candidates and account is not None and account.get("health_band") == "red":
        if firing:
            # Signals fire, but no play responds to them: only a person can.
            reason = "Signals are firing, but no play responds to them, so nothing automatic "
            reason += "will happen. A person should decide whether a play is missing."
        else:
            reason = "No signal has crossed its threshold, so nothing automatic will happen. "
            reason += "A person should decide whether the signals need a new rule."
        return {
            "action": "Review this customer: its health is red, and no play is acting on it.",
            "who": queues["pooled_csm"]["name"],
            "why": f"Health {account['health_score']:.0f} out of 100. {reason}",
            "also": [],
        }
    if not candidates:
        return {
            "action": "No action needed today.",
            "who": "Nobody",
            "why": "No signal is firing for this customer, and no play or task is open.",
            "also": [],
        }
    first, *rest = candidates
    return {**first, "also": [f"{c['action']} Why: {c['why']}" for c in rest]}


def _open_tasks(store, account_id: str, queues: dict) -> list[dict]:
    rows = store.rows(
        "SELECT * FROM ctas WHERE account_id = :id AND status <> 'resolved' ORDER BY sla_due_on",
        id=account_id,
    )
    found = []
    for task in rows:
        packet = json.loads(task["packet"])
        step = packet.get("recommended_next_step") or task["title"]
        found.append(
            {
                "action": f"{step.rstrip('.')}. Due by {task['sla_due_on']}.",
                "who": queues.get(task["queue"], {}).get("name", task["queue"]),
                "why": f'Task {task["cta_id"]} is waiting for a person: "{task["title"]}".',
            }
        )
    return found


def _drafts(store, account_id: str, catalog, queues: dict) -> list[dict]:
    rows = store.rows(
        "SELECT * FROM drafts WHERE account_id = :id AND status = 'pending'", id=account_id
    )
    return [
        {
            "action": f'Approve or reject the draft "{draft["subject"]}".',
            "who": queues.get(draft["queue"], {}).get("name", draft["queue"]),
            "why": f"The play {_play_name(catalog, draft['play_id'])} wrote it, and nothing "
            "is sent until a person decides.",
        }
        for draft in rows
    ]


def _plays_in_motion(store, account_id: str, catalog) -> list[dict]:
    rows = store.rows(
        "SELECT * FROM enrollments WHERE account_id = :id AND status IN ('active', 'holdout') "
        "ORDER BY enrolled_on DESC",
        id=account_id,
    )
    found = []
    for row in rows:
        name = _play_name(catalog, row["play_id"])
        if row["status"] == "holdout":
            window = catalog.play(row["play_id"]).measurement_window_days
            ends = date.fromisoformat(row["enrolled_on"]) + timedelta(days=window)
            found.append(
                {
                    "action": f"Leave this customer alone for the play {name} until {ends}.",
                    "who": "Nobody",
                    "why": f"It was held out on {row['enrolled_on']} so that the play can be "
                    "measured against customers like it. Contacting it would spoil the "
                    "measurement.",
                }
            )
        else:
            step = row["current_step"].replace("_", " ")
            found.append(
                {
                    "action": f"Let the play {name} continue: next step, {step}, "
                    f"on {row['next_action_on']}.",
                    "who": "The system",
                    "why": f"The customer entered the play on {row['enrolled_on']}: "
                    f"{(row['trigger_evidence'] or '').rstrip('.')}.",
                }
            )
    return found


def _signals(store, account_id: str, catalog, firing: dict[str, str]) -> list[dict]:
    """For each firing signal, the play it starts, in the catalog's order of priority."""
    busy = {
        row["play_id"]
        for row in store.rows(
            "SELECT play_id FROM enrollments WHERE account_id = :id "
            "AND status IN ('active', 'holdout', 'waiting_on_human')",
            id=account_id,
        )
    }
    task_open = store.one(
        "SELECT count(*) AS n FROM ctas WHERE account_id = :id AND status <> 'resolved'",
        id=account_id,
    )["n"]
    found = []
    for play in sorted(catalog.plays, key=lambda p: p.priority):
        signal = next((s for s in play.trigger if s in firing), None)
        if signal is None or play.id in busy:
            continue
        decision = store.one(
            "SELECT decision, reason FROM audit_log WHERE account_id = :id AND play_id = :play "
            "ORDER BY run_date DESC LIMIT 1",
            id=account_id,
            play=play.id,
        )
        evidence = firing[signal].rstrip(".")
        waits_for_task = task_open and "open_escalation" in play.exclusions
        if waits_for_task:
            found.append(
                {
                    "action": f"Start the play {play.name} once the open task is closed.",
                    "who": "The system",
                    "why": f"{evidence}. While a person works on this customer, the engine "
                    "starts no new play of this kind for it.",
                }
            )
        elif decision is None or decision["decision"] == "entered":
            found.append(
                {
                    "action": f"Start the play {play.name} at the next daily run.",
                    "who": "The system",
                    "why": f"{evidence}. {play.objective}",
                }
            )
        elif decision["decision"] == "excluded":
            reason = decision["reason"]
            found.append(
                {
                    "action": UNBLOCK.get(reason, f"No contact through the play {play.name}."),
                    "who": "CS Operations" if reason in UNBLOCK else "Nobody",
                    "why": f"{evidence}, but the engine kept the customer out: {reason}.",
                }
            )
    return found


def _play_name(catalog, play_id: str) -> str:
    return next((play.name for play in catalog.plays if play.id == play_id), play_id)
