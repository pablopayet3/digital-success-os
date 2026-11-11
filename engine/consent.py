"""Who may we contact, and how often?

Synthetic data, fictional company. Two rules that every play obeys, enforced
here in code rather than left to each journey:

  Consent         We email a contact only if they opted in and the address works.
                  An opt-out the system learned about itself (an "unsubscribe" reply
                  handled by the mailbox agent) counts at once, before the CRM catches up.
  Frequency cap   At most two outbound touches per contact in any seven days,
                  counted across all plays.
"""

from __future__ import annotations

from engine.context import DayContext

MAX_TOUCHES_PER_7_DAYS = 2
# Who we would rather talk to, best first.
PERSONA_PREFERENCE = ["admin", "champion", "end_user", "billing"]


def can_email(ctx: DayContext, contact: dict) -> bool:
    """Opted in with a working address, and nothing learned since then says otherwise."""
    contact_id = contact["contact_id"]
    learned_otherwise = contact_id in ctx.opted_out or contact_id in ctx.left_company
    return bool(contact["can_email"]) and not learned_otherwise


def emailable_contacts(ctx: DayContext, account_id: str, admins_only: bool = False) -> list[dict]:
    """Contacts on the account we are allowed to email, most suitable first."""
    people = [c for c in ctx.contacts.get(account_id, []) if can_email(ctx, c)]
    if admins_only:
        people = [c for c in people if c["persona"] == "admin"]
    return sorted(people, key=lambda c: (PERSONA_PREFERENCE.index(c["persona"]), c["contact_id"]))


def best_contact(ctx: DayContext, account_id: str) -> dict | None:
    """The person a human should call: someone emailable if possible, else anyone."""
    emailable = emailable_contacts(ctx, account_id)
    if emailable:
        return emailable[0]
    everyone = sorted(
        ctx.contacts.get(account_id, []),
        key=lambda c: (PERSONA_PREFERENCE.index(c["persona"]), c["contact_id"]),
    )
    return everyone[0] if everyone else None


def touches_in_last_7_days(ctx: DayContext, contact_id: str) -> int:
    found = ctx.store.one(
        "SELECT count(*) AS n FROM touches WHERE contact_id = :contact AND touch_date > :since",
        contact=contact_id,
        since=ctx.days_ago(7),
    )
    return found["n"]


def over_frequency_cap(ctx: DayContext, contact_id: str) -> bool:
    return touches_in_last_7_days(ctx, contact_id) >= MAX_TOUCHES_PER_7_DAYS
