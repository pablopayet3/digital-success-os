"""The channels a journey can use to reach a customer.

Synthetic data, fictional company. Nothing here really sends anything:

  email    the rendered message is written to outbox/ so it can be read and checked
  in_app   the prompt is recorded as a touch
  agent    the conversation is run by the agents package (Phase 5)

Every delivery is recorded in the `touches` table. That table is what the
frequency cap counts, what a handoff packet lists under "what was tried", and
what the simulated customers react to.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from engine.catalog import TEMPLATE_DIR
from engine.context import DayContext
from engine.handoff import SETUP_STEPS

FOOTER = (
    "\n\n--\nLumen Labs Success Team\n"
    "(Fictional company. Synthetic demo data. Not a real email.)\n"
)
NEXT_EDITION = {"free": "Standard", "standard": "Premium", "premium": "Enterprise"}


@dataclass
class AgentResult:
    outcome: str  # resolved | escalated | no_uptake | unavailable
    summary: str = ""
    reason_code: str | None = None  # why it escalated
    customer_quote: str | None = None
    cta_id: str | None = None  # set when the agent itself created the handoff


def render_template(
    template: str, account: dict, contact: dict | None, evidence: str | None
) -> tuple[str, str]:
    """Fill a template. Returns (subject, body). The first line of a template is its subject."""
    raw = (TEMPLATE_DIR / f"{template}.md").read_text(encoding="utf-8")
    missing = [label for column, label in SETUP_STEPS.items() if not account[column]]
    missing_steps = "\n".join(f"- {step.capitalize()}" for step in missing)
    filled = raw.format(
        first_name=contact["full_name"].split()[0] if contact else "there",
        account_name=account["account_name"],
        edition=account["edition"].capitalize(),
        next_edition=NEXT_EDITION.get(account["edition"], "Enterprise"),
        missing_steps=missing_steps or "- Nothing missing",
        evidence=evidence or "",
        seats_assigned=account["seats_assigned"],
        seats_licensed=account["seats_licensed"],
    )
    subject, _, body = filled.partition("\n")
    return subject.removeprefix("Subject:").strip(), body.strip()


def send_email(ctx: DayContext, enrollment: dict, step, account: dict, contact: dict) -> str:
    """Render an email into outbox/ and record the touch. Returns the subject."""
    evidence = enrollment["trigger_evidence"]
    subject, body = render_template(step.template, account, contact, evidence)
    folder: Path = ctx.data_dir / "outbox" / ctx.day
    folder.mkdir(parents=True, exist_ok=True)
    message = f"To: {contact['email']}\nSubject: {subject}\n\n{body}{FOOTER}"
    file_name = f"{enrollment['play_id']}_{account['account_id']}_{step.id}.txt"
    (folder / file_name).write_text(message, encoding="utf-8")
    record_touch(ctx, enrollment, step, contact, "email", subject=subject)
    return subject


def show_in_app(ctx: DayContext, enrollment: dict, step, account: dict, contact) -> None:
    """Record an in-product prompt."""
    subject, _ = render_template(step.template, account, contact, enrollment["trigger_evidence"])
    record_touch(ctx, enrollment, step, contact, "in_app", subject=subject)


def record_touch(ctx: DayContext, enrollment: dict, step, contact: dict | None, channel: str,
                 subject: str | None = None, outcome: str | None = None) -> None:  # fmt: skip
    ctx.store.insert(
        "touches",
        {
            "touch_id": ctx.store.next_id("touches", "TCH"),
            "touch_date": ctx.day,
            "account_id": enrollment["account_id"],
            "contact_id": contact["contact_id"] if contact else None,
            "play_id": enrollment["play_id"],
            "enrollment_id": enrollment["enrollment_id"],
            "step_id": step.id,
            "channel": channel,
            "tier": step.tier,
            "template": step.template or step.agent,
            "subject": subject,
            "outcome": outcome,
        },
    )


# The agents package registers its runner here when it is loaded (Phase 5).
# Until then, or if it cannot run, the journey takes the documented fallback:
# an agent that is unavailable hands off to a human. It never guesses.
_agent_runner = None


def register_agent_runner(runner) -> None:
    global _agent_runner
    _agent_runner = runner


def run_agent(ctx: DayContext, enrollment: dict, step, account: dict, contact) -> AgentResult:
    if _agent_runner is None:
        return AgentResult(outcome="unavailable", summary="No agent is available for this step.")
    return _agent_runner(ctx, enrollment, step, account, contact)
