"""The journey runner: move every enrolled account one step further, if it is due.

Synthetic data, fictional company. Journeys are defined in config/journeys.yaml.

Once a day, for each active enrolment whose next action is due:

  1. Has the journey's goal been reached?  -> leave, "goal_reached"
  2. Run the current step. Some steps finish at once (email, in-app, branch) and
     the runner carries straight on to the next; others stop the journey for now:
         wait   until a date
         agent  until the conversation ends (it may escalate)
         cta    until a human resolves the task (the return signal resumes it)

Before any email, the runner re-checks consent, the frequency cap and whether the
account is paused. A touch that is not allowed today is deferred to tomorrow, and
the reason is logged.
"""

from __future__ import annotations

from datetime import date

from engine import channels, consent
from engine.catalog import Journey, Step
from engine.context import DayContext
from engine.handoff import create_cta

TIER_ORDER = ["digital", "agentic", "human"]
MAX_STEPS_PER_DAY = 10  # a guard against a journey that loops


def advance_journeys(ctx: DayContext) -> dict[str, int]:
    """Run every due journey step. Returns counts of what happened."""
    counts = {"emails": 0, "in_app": 0, "agent_conversations": 0, "ctas": 0, "deferred": 0,
              "goal_reached": 0, "exited": 0}  # fmt: skip
    _close_finished_holdouts(ctx)

    due = ctx.store.rows(
        "SELECT * FROM enrollments WHERE status = 'active' AND next_action_on <= :today "
        "ORDER BY enrollment_id",
        today=ctx.day,
    )
    for enrollment in due:
        journey = ctx.catalog.journeys[ctx.catalog.play(enrollment["play_id"]).journey]
        account = ctx.accounts.get(enrollment["account_id"])
        if account is None:
            _close(ctx, enrollment, "exited", "account no longer active")
            counts["exited"] += 1
            continue

        for _ in range(MAX_STEPS_PER_DAY):
            if goal_reached(ctx, journey, account):
                _close(ctx, enrollment, "completed", "goal_reached")
                counts["goal_reached"] += 1
                break
            step = journey.step(enrollment["current_step"])
            keep_going = run_step(ctx, enrollment, journey, step, account, counts)
            if not keep_going:
                break
    return counts


def run_step(ctx, enrollment: dict, journey: Journey, step: Step, account: dict, counts) -> bool:
    """Run one step. Returns True when the journey should carry on to the next step today."""
    contact = _contact(ctx, enrollment)

    if step.type == "exit":
        _close(ctx, enrollment, "completed", step.reason)
        counts["exited"] += 1
        return False

    if step.type == "wait":
        _move(ctx, enrollment, journey.after(step.id), on=ctx.days_ahead(step.days))
        _log(ctx, enrollment, step, "waiting", f"{step.days} days")
        return False

    if step.type == "branch":
        outcome = check_condition(ctx, step.condition, enrollment, account)
        _log(ctx, enrollment, step, "branch", f"{step.condition} is {outcome}")
        _move(ctx, enrollment, step.then if outcome else step.otherwise)
        return True

    if step.type in ("email", "in_app", "agent"):
        blocked = why_not_now(ctx, step, account, contact)
        if blocked == "no contact we are allowed to reach":
            _close(ctx, enrollment, "exited", blocked)
            counts["exited"] += 1
            return False
        if blocked:
            _move(ctx, enrollment, step.id, on=ctx.days_ahead(1))
            _log(ctx, enrollment, step, "deferred", blocked)
            counts["deferred"] += 1
            return False

    if step.type == "email":
        subject = channels.send_email(ctx, enrollment, step, account, contact)
        _log(ctx, enrollment, step, "email_sent", subject)
        counts["emails"] += 1
    elif step.type == "in_app":
        channels.show_in_app(ctx, enrollment, step, account, contact)
        _log(ctx, enrollment, step, "in_app_shown", step.template)
        counts["in_app"] += 1
    elif step.type == "agent":
        counts["agent_conversations"] += 1
        if not _run_agent_step(ctx, enrollment, step, account, contact, counts):
            return False
    elif step.type == "cta":
        _open_cta(ctx, enrollment, step, account, contact)
        counts["ctas"] += 1
        return False

    _reached(ctx, enrollment, step.tier)
    following = journey.after(step.id)
    if following is None:
        _close(ctx, enrollment, "completed", "sequence_finished")
        counts["exited"] += 1
        return False
    _move(ctx, enrollment, following)
    return True


def goal_reached(ctx: DayContext, journey: Journey, account: dict) -> bool:
    """A journey ends as soon as its goal is met, whatever step it is on."""
    goal = journey.goal
    if not goal:
        return False
    if goal["metric"] == "signal_cleared":
        return goal["signal"] not in ctx.signals.get(account["account_id"], {})
    return (account.get(goal["metric"]) or 0) >= goal["at_least"]


def check_condition(ctx: DayContext, condition: str, enrollment: dict, account: dict) -> bool:
    """Evaluate a branch condition against today's data."""
    firing = ctx.signals.get(account["account_id"], {})
    if condition.startswith("signal:"):
        return condition.removeprefix("signal:") in firing
    if condition == "negative_sentiment":
        return "detractor" in firing or "support_friction" in firing
    if condition == "contact_replied":
        return bool((account.get("email_replies_30d") or 0) > 0)
    raise ValueError(f"Unknown branch condition: {condition}")


def why_not_now(ctx: DayContext, step: Step, account: dict, contact: dict | None) -> str | None:
    """Consent, pause and frequency checks made immediately before a touch."""
    if step.type == "in_app":
        return None  # shown inside the product: no email consent needed
    if contact is None or not consent.can_email(ctx, contact):
        return "no contact we are allowed to reach"
    if account["account_id"] in ctx.paused:
        return "account is paused (no reachable admin or an open complaint)"
    if consent.over_frequency_cap(ctx, contact["contact_id"]):
        return "frequency cap: two touches in the last seven days"
    return None


def _run_agent_step(ctx, enrollment, step, account, contact, counts) -> bool:
    """Hand the contact to an AI agent. Returns True when the journey carries on."""
    result = channels.run_agent(ctx, enrollment, step, account, contact)
    channels.record_touch(ctx, enrollment, step, contact, "agent", outcome=result.outcome)
    _log(ctx, enrollment, step, f"agent_{result.outcome}", result.summary)
    _reached(ctx, enrollment, "agentic")
    if result.outcome in ("resolved", "no_uptake"):
        return True

    # Escalated, or the agent could not run: a human takes over, with the full context.
    if result.cta_id is None:
        create_cta(
            ctx,
            account["account_id"],
            queue="pooled_csm",
            priority="normal",
            reason_code=result.reason_code or "agent_unavailable",
            title="Agent handed off an onboarding conversation",
            next_step="Pick up where the agent stopped; the summary says what was tried.",
            source="agent",
            enrollment=enrollment,
            step_id=step.id,
            contact=contact,
            conversation_summary=result.summary,
            customer_quote=result.customer_quote,
        )
    counts["ctas"] += 1
    _reached(ctx, enrollment, "human")
    ctx.store.update(
        "enrollments", {"enrollment_id": enrollment["enrollment_id"]}, status="waiting_on_human"
    )
    enrollment["status"] = "waiting_on_human"
    return False


def _open_cta(ctx, enrollment, step: Step, account: dict, contact: dict | None) -> None:
    """Create the human task for a journey step and park the journey until it is resolved."""
    brief = None
    if step.with_brief:
        from agents.briefs import write_brief  # imported here: agents depends on engine

        brief = write_brief(ctx, account, enrollment)
    cta_id = create_cta(
        ctx,
        account["account_id"],
        queue=step.queue,
        priority=step.priority,
        reason_code=step.reason_code,
        title=step.title,
        next_step=step.next_step,
        enrollment=enrollment,
        step_id=step.id,
        contact=contact or consent.best_contact(ctx, account["account_id"]),
        brief=brief,
    )
    if step.pause_account:
        account_id = account["account_id"]
        ctx.store.execute("DELETE FROM paused_accounts WHERE account_id = :id", id=account_id)
        ctx.store.insert(
            "paused_accounts",
            {"account_id": account_id, "reason": step.reason_code,
             "paused_on": ctx.day, "cta_id": cta_id},
        )  # fmt: skip
        ctx.paused.add(account_id)
    _log(ctx, enrollment, step, "cta_created", f"{cta_id} -> {step.queue}")
    _reached(ctx, enrollment, "human")
    ctx.store.update(
        "enrollments", {"enrollment_id": enrollment["enrollment_id"]}, status="waiting_on_human"
    )
    enrollment["status"] = "waiting_on_human"


def _close_finished_holdouts(ctx: DayContext) -> None:
    """A holdout stays reserved for the play's measurement window, then is released."""
    for row in ctx.store.rows("SELECT * FROM enrollments WHERE status = 'holdout'"):
        window = ctx.catalog.play(row["play_id"]).measurement_window_days
        if (ctx.today - date.fromisoformat(row["enrolled_on"])).days >= window:
            _close(ctx, row, "completed", "measurement window over")


def _contact(ctx: DayContext, enrollment: dict) -> dict | None:
    people = ctx.contacts.get(enrollment["account_id"], [])
    return next((c for c in people if c["contact_id"] == enrollment["contact_id"]), None)


def _move(ctx, enrollment: dict, step_id: str, on: str | None = None) -> None:
    """Point the enrolment at its next step, due today unless a date is given."""
    enrollment["current_step"], enrollment["next_action_on"] = step_id, on or ctx.day
    ctx.store.update(
        "enrollments",
        {"enrollment_id": enrollment["enrollment_id"]},
        current_step=step_id,
        next_action_on=enrollment["next_action_on"],
    )


def _reached(ctx, enrollment: dict, tier: str | None) -> None:
    """Remember the highest rung of the intervention ladder this enrolment has reached."""
    current = enrollment["highest_tier"]
    if tier and (current is None or TIER_ORDER.index(tier) > TIER_ORDER.index(current)):
        enrollment["highest_tier"] = tier
        ctx.store.update(
            "enrollments", {"enrollment_id": enrollment["enrollment_id"]}, highest_tier=tier
        )


def _close(ctx, enrollment: dict, status: str, reason: str) -> None:
    enrollment["status"] = status
    ctx.store.update(
        "enrollments",
        {"enrollment_id": enrollment["enrollment_id"]},
        status=status,
        exit_reason=reason,
        closed_on=ctx.day,
    )
    ctx.store.insert(
        "journey_events",
        {
            "event_date": ctx.day,
            "enrollment_id": enrollment["enrollment_id"],
            "account_id": enrollment["account_id"],
            "play_id": enrollment["play_id"],
            "step_id": enrollment["current_step"],
            "event": status,
            "detail": reason,
        },
    )


def _log(ctx, enrollment: dict, step: Step, event: str, detail: str | None) -> None:
    ctx.store.insert(
        "journey_events",
        {
            "event_date": ctx.day,
            "enrollment_id": enrollment["enrollment_id"],
            "account_id": enrollment["account_id"],
            "play_id": enrollment["play_id"],
            "step_id": step.id,
            "event": event,
            "detail": detail,
        },
    )


# --- journey analytics ------------------------------------------------------------------

# Events that mean a step actually reached the customer or a person.
STEP_HAPPENED = ("email_sent", "in_app_shown", "cta_created", "agent_")


def journey_funnel(store, journey: Journey, play_id: str) -> list[dict]:
    """How far accounts got: eligible, entered, each customer-facing step, finished.

    Counts are enrolments, read from the journey's own event log. A step later in the
    journey is not always smaller than the one before it: a branch can skip a step.
    """
    arms = {
        row["arm"]: row["n"]
        for row in store.rows(
            "SELECT arm, count(*) AS n FROM enrollments WHERE play_id = :play GROUP BY arm",
            play=play_id,
        )
    }
    entered, held_out = arms.get("treatment", 0), arms.get("holdout", 0)
    events = store.rows(
        "SELECT step_id, event, enrollment_id FROM journey_events WHERE play_id = :play",
        play=play_id,
    )
    reached: dict[str, set] = {}
    for row in events:
        if row["event"].startswith(STEP_HAPPENED):
            reached.setdefault(row["step_id"], set()).add(row["enrollment_id"])
    finished = store.one(
        "SELECT count(*) AS n FROM enrollments "
        "WHERE play_id = :play AND arm = 'treatment' AND status = 'completed'",
        play=play_id,
    )["n"]

    funnel = [
        {"stage": "Signal fired and eligible", "accounts": entered + held_out},
        {"stage": "Entered the journey (the rest are held out)", "accounts": entered},
    ]
    for step in journey.steps:
        if step.type in ("email", "in_app", "agent", "cta"):
            label = f"{step.type.replace('_', '-')}: {step.id} ({step.tier})"
            funnel.append({"stage": label, "accounts": len(reached.get(step.id, ()))})
    funnel.append({"stage": "Journey completed", "accounts": finished})
    return funnel
