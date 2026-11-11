"""Digital-to-human handoffs: what travels to the human, and what comes back.

Synthetic data, fictional company. See docs/human-fallback.md.

A handoff is a CTA (call to action): a task for a person. Two halves:

  Going out   create_cta() builds a handoff packet with everything the human needs
              (who, why, what was already tried, the customer's own words, a snapshot
              of the account, a recommended next step), routes it to a queue with an
              SLA, and pauses the journey.

  Coming back resolve_cta() records the human's outcome and reason. That is the
              return signal: it decides whether the account re-enters its journey,
              leaves it, or passes to Sales. "The agent should have handled this"
              becomes a new evaluation case, so the agent improves.

The same two functions serve the journey runner, the AI agents, the Human console
and the API. There is one way in and one way out.
"""

from __future__ import annotations

import json
import math
from datetime import date, timedelta

from pydantic import BaseModel

from common.paths import ROOT
from common.store import Store
from common.warehouse import open_warehouse
from engine.context import DayContext, records

FEEDBACK_DIR = ROOT / "evals" / "cases" / "from_feedback"
SETUP_STEPS = {
    "has_first_board": "create a first board",
    "has_five_users": "invite at least five users",
    "has_integration": "connect an integration",
    "has_sso": "configure single sign-on",
}


class HandoffPacket(BaseModel):
    """Everything a human needs to act without asking the customer to repeat themselves."""

    cta_id: str
    account_id: str
    account_name: str
    contact: dict | None  # name, email, persona, role
    trigger: dict  # source (journey, agent, mailbox), play, signal, evidence
    reason_code: str
    conversation_summary: str | None = None  # filled when an agent hands off
    what_was_tried: list[str]
    customer_quote: str | None = None
    account_snapshot: dict  # health and its components, seats, edition, renewal, tickets
    recommended_next_step: str
    brief: str | None = None  # account-owner brief for Sales CTAs (Phase 5)
    priority: str
    queue: str
    sla_due_at: str
    created_at: str


def create_cta(
    ctx: DayContext,
    account_id: str,
    queue: str,
    priority: str,
    reason_code: str,
    title: str,
    next_step: str,
    source: str = "journey",
    enrollment: dict | None = None,
    step_id: str | None = None,
    contact: dict | None = None,
    conversation_summary: str | None = None,
    customer_quote: str | None = None,
    brief: str | None = None,
) -> str:
    """Create a task for a human, with a full handoff packet. Returns the CTA id."""
    account = ctx.accounts[account_id]
    cta_id = ctx.store.next_id("ctas", "CTA")
    sla_days = math.ceil(ctx.catalog.routing["queues"][queue]["sla_hours"] / 24)
    sla_due_on = ctx.days_ahead(sla_days)
    signals = ctx.signals.get(account_id, {})
    trigger_signal = enrollment["trigger_signal"] if enrollment else None

    packet = HandoffPacket(
        cta_id=cta_id,
        account_id=account_id,
        account_name=account["account_name"],
        contact=_contact_card(contact),
        trigger={
            "source": source,
            "play": enrollment["play_id"] if enrollment else None,
            "signal": trigger_signal,
            "evidence": signals.get(trigger_signal) or (enrollment or {}).get("trigger_evidence"),
            "all_signals_firing": signals,
        },
        reason_code=reason_code,
        conversation_summary=conversation_summary,
        what_was_tried=_what_was_tried(ctx.store, enrollment),
        customer_quote=customer_quote or _latest_nps_comment(ctx, account_id),
        account_snapshot=account_snapshot(account),
        recommended_next_step=next_step,
        brief=brief,
        priority=priority,
        queue=queue,
        sla_due_at=sla_due_on,
        created_at=ctx.day,
    )
    ctx.store.insert(
        "ctas",
        {
            "cta_id": cta_id,
            "account_id": account_id,
            "contact_id": contact["contact_id"] if contact else None,
            "play_id": enrollment["play_id"] if enrollment else None,
            "enrollment_id": enrollment["enrollment_id"] if enrollment else None,
            "step_id": step_id,
            "source": source,
            "queue": queue,
            "priority": priority,
            "reason_code": reason_code,
            "title": title,
            "packet": packet.model_dump_json(),
            "status": "open",
            "created_on": ctx.day,
            "sla_due_on": sla_due_on,
            "picked_up_on": None,
            "resolved_on": None,
            "outcome": None,
            "outcome_notes": None,
            "resolved_by": None,
            "next_state": None,
        },
    )
    return cta_id


def resolve_cta(
    store: Store, catalog, cta_id: str, outcome: str, today: date, notes: str = "",
    resolved_by: str = "human", export_eval_case: bool = False,
) -> dict:  # fmt: skip
    """Record the human's outcome and send the return signal to the journey.

    Returns {"next_state": ..., "enrollment_status": ...}.
    With export_eval_case=True, an "agent should have handled this" outcome is also
    written to evals/cases/from_feedback/ as a draft test case (the Human console
    does this; the simulated staff only fill the review queue).
    """
    outcomes = catalog.routing["outcomes"]
    if outcome not in outcomes:
        raise ValueError(f"Unknown outcome '{outcome}'. Use one of: {', '.join(outcomes)}")
    cta = store.one("SELECT * FROM ctas WHERE cta_id = :id", id=cta_id)
    if cta is None:
        raise ValueError(f"No CTA with id {cta_id}")
    if cta["status"] == "resolved":
        raise ValueError(f"{cta_id} is already resolved")

    day = today.isoformat()
    next_state = outcomes[outcome]["next_state"]
    store.update(
        "ctas",
        {"cta_id": cta_id},
        status="resolved",
        picked_up_on=cta["picked_up_on"] or day,
        resolved_on=day,
        outcome=outcome,
        outcome_notes=notes,
        resolved_by=resolved_by,
        next_state=next_state,
    )
    # A CTA that put the account's emails on hold releases them when it closes well.
    if outcome in ("resolved", "saved"):
        store.execute("DELETE FROM paused_accounts WHERE cta_id = :id", id=cta_id)

    enrollment_status = None
    if cta["enrollment_id"]:
        enrollment_status = _return_to_journey(store, catalog, cta, outcome, next_state, today)

    if outcome == "agent_should_have_handled":
        _queue_as_eval_candidate(store, cta, notes, day, export_eval_case)
    return {"next_state": next_state, "enrollment_status": enrollment_status}


def _return_to_journey(store, catalog, cta, outcome, next_state, today) -> str | None:
    """The return signal: move the waiting enrollment on, according to the outcome."""
    enrollment = store.one(
        "SELECT * FROM enrollments WHERE enrollment_id = :id", id=cta["enrollment_id"]
    )
    if enrollment is None or enrollment["status"] != "waiting_on_human":
        return None
    day = today.isoformat()
    journey = catalog.journeys[catalog.play(enrollment["play_id"]).journey]
    following_step = journey.after(cta["step_id"]) if cta["step_id"] else None

    if next_state == "re_enter_journey" and following_step:
        changes = {
            "status": "active",
            "current_step": following_step,
            "next_action_on": (today + timedelta(days=1)).isoformat(),
        }
    elif next_state == "exit":
        changes = {"status": "exited", "exit_reason": f"human: {outcome}", "closed_on": day}
    else:  # Sales owns it, or the journey had nothing left after the human step
        changes = {"status": "completed", "exit_reason": f"human: {outcome}", "closed_on": day}
    store.update("enrollments", {"enrollment_id": enrollment["enrollment_id"]}, **changes)
    store.insert(
        "journey_events",
        {
            "event_date": day,
            "enrollment_id": enrollment["enrollment_id"],
            "account_id": enrollment["account_id"],
            "play_id": enrollment["play_id"],
            "step_id": cta["step_id"],
            "event": "return_signal",
            "detail": f"{outcome} -> {next_state}",
        },
    )
    return changes["status"]


def check_queue_capacity(ctx: DayContext) -> list[dict]:
    """Raise an alert for every queue holding more open work than two days of capacity."""
    alerts = []
    open_by_queue = {
        row["queue"]: row["n"]
        for row in ctx.store.rows(
            "SELECT queue, count(*) AS n FROM ctas WHERE status <> 'resolved' GROUP BY queue"
        )
    }
    for queue, settings in ctx.catalog.routing["queues"].items():
        open_ctas, capacity = open_by_queue.get(queue, 0), settings["capacity_per_day"]
        if open_ctas > 2 * capacity:
            alerts.append(
                {
                    "alert_date": ctx.day,
                    "queue": queue,
                    "open_ctas": open_ctas,
                    "capacity_per_day": capacity,
                    "message": f"{settings['name']}: {open_ctas} open CTAs, "
                    f"capacity {capacity} a day. Working by priority, then SLA.",
                }
            )
    ctx.store.insert("queue_alerts", *alerts)
    return alerts


def account_snapshot(account: dict) -> dict:
    """The account at a glance, for the handoff packet."""
    missing = [label for column, label in SETUP_STEPS.items() if not account[column]]
    return {
        "segment": account["segment"],
        "coverage_tier": account["coverage_tier"],
        "edition": account["edition"],
        "lifecycle_stage": account["lifecycle_stage"],
        "arr": account["arr"],
        "renewal_date": (account["renewal_date"] or "")[:10],
        "days_to_renewal": account["days_to_renewal"],
        "account_owner": account["account_owner"],
        "health": {
            "score": account["health_score"],
            "band": account["health_band"],
            "adoption": account["health_adoption"],
            "engagement": account["health_engagement"],
            "sentiment": account["health_sentiment"],
            "support": account["health_support"],
            "commercial": account["health_commercial"],
        },
        "seats": {
            "licensed": account["seats_licensed"],
            "assigned": account["seats_assigned"],
            "utilisation": account["seat_utilisation"],
            "monthly_active_users": account["mau_30d"],
            "monthly_active_users_30_days_ago": account["mau_prior_30d"],
        },
        "setup": {
            "closure_pct": account["prerequisite_closure_pct"],
            "missing_steps": missing,
        },
        "support": {
            "tickets_30d": account["tickets_30d"],
            "open_high_priority_tickets": account["open_high_priority_tickets"],
        },
        "latest_nps_score": account["latest_nps_score"],
        "churn_risk": {
            "score": account["churn_risk_score"],
            "reasons": account["churn_top_reasons"],
        },
        "expansion": {
            "score": account["expansion_score"],
            "reasons": account["expansion_top_reasons"],
        },
    }


def _contact_card(contact: dict | None) -> dict | None:
    if contact is None:
        return None
    return {key: contact[key] for key in ("contact_id", "full_name", "email", "persona", "role")}


def _what_was_tried(store: Store, enrollment: dict | None) -> list[str]:
    """The touches this journey already delivered, oldest first, in plain words."""
    if enrollment is None:
        return []
    touches = store.rows(
        "SELECT * FROM touches WHERE enrollment_id = :id ORDER BY touch_date, touch_id",
        id=enrollment["enrollment_id"],
    )
    tried = []
    for touch in touches:
        what = f"{touch['touch_date']}: {touch['channel']}"
        if touch["template"]:
            what += f" '{touch['template']}'"
        if touch["outcome"]:
            what += f" ({touch['outcome']})"
        tried.append(what)
    return tried


def _latest_nps_comment(ctx: DayContext, account_id: str) -> str | None:
    """The customer's own words, if they left an NPS comment in the last 30 days."""
    warehouse = open_warehouse(ctx.data_dir)
    found = records(
        warehouse.query(
            f"""
            SELECT score, comment FROM silver.stg_nps
            WHERE account_id = '{account_id}' AND comment IS NOT NULL
              AND responded_date > DATE '{ctx.days_ago(30)}'
            ORDER BY responded_at DESC LIMIT 1
            """
        )
    )
    warehouse.close()
    return f"NPS {found[0]['score']}: \"{found[0]['comment']}\"" if found else None


def _queue_as_eval_candidate(store: Store, cta: dict, notes: str, day: str, export: bool) -> None:
    """The feedback loop: a handoff a human says was unnecessary becomes an eval case."""
    store.insert(
        "eval_candidates",
        {
            "cta_id": cta["cta_id"],
            "created_on": day,
            "source": "human said: agent should have handled this",
            "reason_code": cta["reason_code"],
            "human_notes": notes,
            "packet": cta["packet"],
        },
    )
    if export:
        FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
        case = {
            "id": f"feedback_{cta['cta_id']}",
            "source": "human said: agent should have handled this",
            "reason_code_at_handoff": cta["reason_code"],
            "human_notes": notes,
            "expected_behavior": "answer without handing off",
            "packet": json.loads(cta["packet"]),
            "status": "needs_review",  # a person turns it into a proper test case
        }
        path = FEEDBACK_DIR / f"{cta['cta_id']}.json"
        path.write_text(json.dumps(case, indent=2), encoding="utf-8")
