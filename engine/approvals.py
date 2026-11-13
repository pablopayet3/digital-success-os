"""Drafts that wait for a person's approval before they reach a customer.

Synthetic data, fictional company. Some messages carry more risk than a setup guide:
asking a customer to act as a reference, for example. A journey step marked
`approval: <queue>` does not send its email. It writes a draft, parks the journey, and
puts the draft in that queue's approval list in the Human console. Nothing reaches the
customer until a person approves it (ADR 0029).

    approve -> the journey resumes; the next run sends the email (consent and the
               frequency cap are checked again at that moment)
    reject  -> the journey ends for this customer, with the reason "draft_rejected"

In a simulation that runs many days on its own, simulated staff decide the drafts
(work_approvals), as they work the task queues.
"""

from __future__ import annotations

import hashlib

from engine.assignment import bucket
from engine.channels import render_template
from engine.context import DayContext

APPROVAL_RATE = 0.85  # simulated staff approve this share of drafts; the rest are rejected


def approved_draft(ctx: DayContext, enrollment: dict, step) -> dict | None:
    """The approved draft for this step of this enrolment, if a person approved one."""
    return ctx.store.one(
        "SELECT * FROM drafts WHERE enrollment_id = :enrollment AND step_id = :step "
        "AND status = 'approved'",
        enrollment=enrollment["enrollment_id"],
        step=step.id,
    )


def create_draft(ctx: DayContext, enrollment: dict, step, account: dict, contact: dict) -> str:
    """Write the email as a draft for the step's approval queue. Returns the draft id."""
    subject, body = render_template(step.template, account, contact, enrollment["trigger_evidence"])
    seed = f"{enrollment['enrollment_id']}:{step.id}"
    draft_id = "DRF-" + hashlib.sha256(seed.encode()).hexdigest()[:8].upper()
    ctx.store.insert(
        "drafts",
        {
            "draft_id": draft_id,
            "created_on": ctx.day,
            "account_id": account["account_id"],
            "contact_id": contact["contact_id"],
            "play_id": enrollment["play_id"],
            "enrollment_id": enrollment["enrollment_id"],
            "step_id": step.id,
            "queue": step.approval,
            "recipient": contact["email"],
            "subject": subject,
            "body": body,
            "status": "pending",
        },
    )
    return draft_id


def decide(store, draft_id: str, approved: bool, day: str, by: str, notes: str = "") -> dict:
    """Record a person's decision on a draft, and move the journey on accordingly."""
    draft = store.one("SELECT * FROM drafts WHERE draft_id = :id", id=draft_id)
    if draft is None or draft["status"] != "pending":
        raise ValueError(f"{draft_id} is not waiting for a decision")
    status = "approved" if approved else "rejected"
    store.update(
        "drafts",
        {"draft_id": draft_id},
        status=status,
        decided_on=day,
        decided_by=by,
        notes=notes,
    )
    where = {"enrollment_id": draft["enrollment_id"]}
    if approved:
        # The journey resumes at the same step, which now finds an approved draft.
        store.update("enrollments", where, status="active", next_action_on=day)
        event = "draft_approved"
    else:
        store.update(
            "enrollments", where, status="exited", exit_reason="draft_rejected", closed_on=day
        )
        event = "draft_rejected"
    store.insert(
        "journey_events",
        {
            "event_date": day,
            "enrollment_id": draft["enrollment_id"],
            "account_id": draft["account_id"],
            "play_id": draft["play_id"],
            "step_id": draft["step_id"],
            "event": event,
            "detail": f"{draft_id} by {by}" + (f": {notes}" if notes else ""),
        },
    )
    return {**draft, "status": status}


def mark_sent(ctx: DayContext, enrollment: dict, step) -> None:
    ctx.store.update(
        "drafts",
        {"enrollment_id": enrollment["enrollment_id"], "step_id": step.id, "status": "approved"},
        status="sent",
    )


def work_approvals(ctx: DayContext) -> int:
    """Simulated staff decide the drafts written before today. Returns how many."""
    waiting = ctx.store.rows(
        "SELECT draft_id FROM drafts WHERE status = 'pending' AND created_on < :today "
        "ORDER BY draft_id",
        today=ctx.day,
    )
    for row in waiting:
        approve = bucket(row["draft_id"], "draft_decision") < APPROVAL_RATE
        notes = "" if approve else "Not the right moment to ask this customer."
        decide(ctx.store, row["draft_id"], approve, ctx.day, "simulated staff", notes)
    return len(waiting)
