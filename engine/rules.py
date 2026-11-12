"""The rules engine: which account enters which play today, and why.

Synthetic data, fictional company.

Once a day, for every play (highest priority first) and every account with one
of the play's trigger signals firing, the engine walks through the same checks:

    1. Is the account in a segment the pilot covers?         (config/rollout.yaml)
    2. Does it match the play's audience?                    (lifecycle, edition)
    3. Does any exclusion apply?                             (already in a play, open
                                                              escalation, renewal being
                                                              negotiated, nobody to email)
    4. Is it inside the play's rollout stage?                (10% slice, or full)
    5. Treatment or holdout?                                 (deterministic hash)

Every decision is written to the audit log with its reason, including the
accounts that were kept out. "Why didn't this account get the play?" always has
an answer.
"""

from __future__ import annotations

from datetime import date

from engine import consent
from engine.assignment import assign_arm, in_rollout
from engine.catalog import Play
from engine.context import DayContext

OPEN_STATUSES = ("active", "waiting_on_human", "holdout")


def evaluate_plays(ctx: DayContext) -> dict[str, int]:
    """Enrol accounts into plays for today. Returns counts of each kind of decision."""
    state = _EngineState(ctx)
    counts = {"entered": 0, "holdout": 0, "excluded": 0}
    audit_rows = []

    for play in ctx.catalog.plays:
        journey = ctx.catalog.journeys[play.journey]
        for account_id, account in ctx.accounts.items():
            firing = [s for s in play.trigger if s in ctx.signals.get(account_id, {})]
            if not firing or account["coverage_tier"] not in ctx.segments:
                continue

            reason = why_not(ctx, state, play, account)
            if reason == "already in this play":
                continue  # not a decision worth logging every day
            if reason is None and not in_rollout(account_id, play):
                reason = "outside the 10% rollout slice"
            if reason is not None:
                audit_rows.append(_audit(ctx, account_id, play, "excluded", reason))
                counts["excluded"] += 1
                continue

            arm = assign_arm(account_id, play)
            contact = _target_contact(ctx, play, account_id)
            enrollment = {
                "enrollment_id": f"{play.id}:{account_id}:v{play.version}:{ctx.day}",
                "account_id": account_id,
                "play_id": play.id,
                "play_version": play.version,
                "arm": arm,
                "rollout_stage": play.rollout_stage,
                "status": "active" if arm == "treatment" else "holdout",
                "exit_reason": None,
                "trigger_signal": firing[0],
                "trigger_evidence": ctx.signals[account_id][firing[0]],
                "contact_id": contact["contact_id"] if contact else None,
                "current_step": journey.steps[0].id if arm == "treatment" else None,
                "next_action_on": ctx.day if arm == "treatment" else None,
                "highest_tier": None,
                "enrolled_on": ctx.day,
                "closed_on": None,
            }
            ctx.store.insert("enrollments", enrollment)
            state.remember(enrollment)
            if arm == "treatment":
                audit_rows.append(_audit(ctx, account_id, play, "entered", f"signal {firing[0]}"))
                counts["entered"] += 1
            else:
                audit_rows.append(
                    _audit(ctx, account_id, play, "holdout", "would have entered; held out")
                )
                counts["holdout"] += 1

    ctx.store.insert("audit_log", *audit_rows)
    return counts


def preview_segment(ctx: DayContext, segment: str) -> list[dict]:
    """What would happen today if one more coverage tier joined the pilot. Writes nothing.

    The same checks as evaluate_plays, in the same order, on the accounts of that tier.
    One row per play: how many would enter, how many the hash would hold out, how many
    a rule would keep out, and the queue the play's first step would load on day one
    (when that first step is a task for a person).
    """
    state = _EngineState(ctx)
    rows = []
    for play in ctx.catalog.plays:
        first_step = ctx.catalog.journeys[play.journey].steps[0]
        row = {
            "play_id": play.id,
            "play": play.name,
            "would_enter": 0,
            "would_be_held_out": 0,
            "kept_out_by_a_rule": 0,
            "first_day_queue": first_step.queue if first_step.type == "cta" else None,
        }
        for account_id, account in ctx.accounts.items():
            firing = [s for s in play.trigger if s in ctx.signals.get(account_id, {})]
            if not firing or account["coverage_tier"] != segment:
                continue
            reason = why_not(ctx, state, play, account)
            if reason is None and not in_rollout(account_id, play):
                reason = "outside the 10% rollout slice"
            if reason is not None:
                row["kept_out_by_a_rule"] += 1
                continue
            arm = assign_arm(account_id, play)
            row["would_enter" if arm == "treatment" else "would_be_held_out"] += 1
            # Kept in memory for the rest of the preview, so that "one exclusive play
            # per account" holds here as it would in a real run. Never stored.
            state.remember(
                {
                    "account_id": account_id,
                    "play_id": play.id,
                    "status": "active" if arm == "treatment" else "holdout",
                    "enrolled_on": ctx.day,
                    "closed_on": None,
                }
            )
        rows.append(row)
    return rows


def why_not(ctx: DayContext, state: _EngineState, play: Play, account: dict) -> str | None:
    """The reason this account may not enter this play today, or None if it may."""
    account_id = account["account_id"]

    lifecycles = play.audience.get("lifecycle")
    if lifecycles and account["lifecycle_stage"] not in lifecycles:
        return f"lifecycle stage '{account['lifecycle_stage']}' is not in the audience"
    editions = play.audience.get("editions")
    if editions and account["edition"] not in editions:
        return f"edition '{account['edition']}' is not in the audience"

    for rule in play.exclusions:
        if rule == "already_in_this_play" and state.in_this_play(account_id, play, ctx.today):
            return "already in this play"
        if rule == "in_another_play" and state.in_another_exclusive_play(account_id, play):
            return "already in another play"
        if rule == "open_escalation" and account_id in state.open_escalations:
            return "an escalation is open with a human"
        if rule == "renewal_in_negotiation" and account["renewal_in_negotiation"]:
            return "renewal is being negotiated"
        if rule == "no_emailable_admin":
            if not consent.emailable_contacts(ctx, account_id, admins_only=True):
                return "no admin we are allowed to email"
        if rule == "no_emailable_contact" and not consent.emailable_contacts(ctx, account_id):
            return "no contact we are allowed to email"
    return None


def _target_contact(ctx: DayContext, play: Play, account_id: str) -> dict | None:
    """Who this play will talk to: an admin for onboarding, otherwise the best contact."""
    if "no_emailable_admin" in play.exclusions:
        return consent.emailable_contacts(ctx, account_id, admins_only=True)[0]
    return consent.best_contact(ctx, account_id)


def _audit(ctx: DayContext, account_id: str, play: Play, decision: str, reason: str) -> dict:
    return {
        "run_date": ctx.day,
        "account_id": account_id,
        "play_id": play.id,
        "decision": decision,
        "reason": reason,
    }


class _EngineState:
    """What the engine has already decided, kept in memory for the length of one run."""

    def __init__(self, ctx: DayContext):
        self.ctx = ctx
        self.enrollments: dict[str, list[dict]] = {}
        for row in ctx.store.rows("SELECT * FROM enrollments"):
            self.remember(row)
        escalations = ctx.store.rows(
            "SELECT DISTINCT account_id FROM ctas "
            "WHERE status <> 'resolved' AND priority IN ('urgent', 'high')"
        )
        self.open_escalations = {row["account_id"] for row in escalations}

    def remember(self, enrollment: dict) -> None:
        self.enrollments.setdefault(enrollment["account_id"], []).append(enrollment)

    def in_this_play(self, account_id: str, play: Play, today: date) -> bool:
        """Open in this play now, or left it within the cool-down period."""
        for enrollment in self.enrollments.get(account_id, []):
            if enrollment["play_id"] != play.id:
                continue
            if enrollment["status"] in OPEN_STATUSES:
                return True
            closed = date.fromisoformat(enrollment["closed_on"] or enrollment["enrolled_on"])
            if (today - closed).days < play.cooldown_days:
                return True
        return False

    def in_another_exclusive_play(self, account_id: str, play: Play) -> bool:
        """One exclusive play at a time. A holdout counts, to keep the comparison clean."""
        for enrollment in self.enrollments.get(account_id, []):
            if enrollment["play_id"] == play.id or enrollment["status"] not in OPEN_STATUSES:
                continue
            if self.ctx.catalog.play(enrollment["play_id"]).exclusive:
                return True
        return False
