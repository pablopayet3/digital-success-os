"""The event log on the Overview: the latest things the system did, in plain words.

Synthetic data, fictional company. Each line says which signal led to which action, for
which customer and in which play, so a reader sees the loop at work without opening a
table of codes. The words come from the journeys' own record of events
(`journey_events`) and from the enrolments, in the operational store.
"""

from __future__ import annotations

from common.config import load_yaml

# The team behind each queue, as the Human console names it.
QUEUE_NAMES = {key: queue["name"] for key, queue in load_yaml("routing.yaml")["queues"].items()}

# What each recorded event means, as the end of a sentence. Events not listed here (a
# wait, a branch) are steps of the machinery, not actions, and are left out.
ACTIONS = {
    "entered": "entered the play",
    "held_out": "was held out of the play, for comparison",
    "email_sent": "was sent an email: {detail}",
    "in_app_shown": "was shown a message inside the product",
    "agent_resolved": "talked to the AI agent, and no person was needed",
    "agent_escalated": "talked to the AI agent, which passed the customer to a person",
    "agent_unavailable": "could not reach the AI agent, so a person took over",
    "cta_created": "was handed to a person, in the queue of the {detail}",
    "draft_created": "was sent nothing yet: a draft waits for a person's approval",
    "draft_approved": "had a draft approved by a person",
    "draft_rejected": "had a draft rejected by a person, so the play ended",
    "deferred": "had a message postponed ({detail})",
    "goal_reached": "reached the play's goal, so the play ended",
}


def latest_events(store, limit: int = 15) -> list[dict]:
    """The most recent actions, newest first, with the signal that started each play."""
    rows = store.rows(
        """
        SELECT events.event_date AS day, events.account_id, events.play_id,
               events.event, events.detail, enrollments.trigger_signal
        FROM journey_events AS events
        JOIN enrollments ON events.enrollment_id = enrollments.enrollment_id
        UNION ALL
        SELECT enrolled_on, account_id, play_id,
               CASE WHEN arm = 'holdout' THEN 'held_out' ELSE 'entered' END,
               NULL, trigger_signal
        FROM enrollments
        """
    )
    shown = []
    for row in rows:
        event = row["event"]
        if event == "completed" and row["detail"] == "goal_reached":
            event = "goal_reached"
        elif event.startswith("agent_") and event not in ACTIONS:
            event = "agent_escalated"
        if event in ACTIONS:
            shown.append({**row, "event": event})
    # Newest first; on the same day, the order of the loop: entry, then the actions.
    order = list(ACTIONS)
    shown.sort(key=lambda r: (r["day"], order.index(r["event"])), reverse=True)
    return shown[:limit]


def sentence(event: dict, account_name: str, signal_name: str, play_name: str) -> str:
    """One event as a sentence: the customer, the action, and why."""
    detail = event.get("detail") or ""
    if event["event"] in ("cta_created", "draft_created") and " -> " in detail:
        # "CTA-1A2B -> pooled_csm" becomes the team's name.
        queue = detail.split(" -> ")[1]
        detail = QUEUE_NAMES.get(queue, queue)
    action = ACTIONS[event["event"]].format(detail=detail)
    return f"{account_name} {action}. Why: {signal_name.lower()}, in the play {play_name}."
