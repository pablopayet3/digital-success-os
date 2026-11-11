"""The mailbox triage agent: read every reply in the shared mailbox and route it.

Synthetic data, fictional company.

Journey emails are sent from a shared address, so replies land in a shared inbox.
If nobody reads it, an "unsubscribe" is ignored, a "we need 20 more seats" goes
unanswered, and a contact who left stays on the list. This agent reads every
reply once.

Two parts, kept apart on purpose:

  The LLM proposes.  A small model classifies each reply: intent, sentiment,
                     confidence, and details such as the number of seats asked for.
  The rules decide.  What happens next comes from config/routing.yaml, the same way
                     every time:

      out of office        ignore; no touch is counted
      unsubscribe          opt the contact out now and end their journeys
      left the company     mark the contact as gone; if no admin is left, open a task
      product question     the onboarding agent answers if it can, otherwise a CTA
      buying intent        Sales CTA, with a brief
      complaint            high-priority CTA for a human, and pause the account's emails
      meeting request      CTA
      low confidence       a person reviews it

Replies that are too old to act on when first read are recorded as "missed".
"""

from __future__ import annotations

import json
from datetime import date

from agents.briefs import write_brief
from agents.classify import classify_replies
from agents.onboarding import converse, scripted
from agents.runner import hand_off, record_conversation
from common.warehouse import open_warehouse
from engine import consent
from engine.context import DayContext, records
from engine.handoff import create_cta


def triage_new_replies(ctx: DayContext) -> dict[str, int]:
    """Classify and route every reply not yet handled. Returns a count per action."""
    done = {row["message_id"] for row in ctx.store.rows("SELECT message_id FROM mailbox_triage")}
    warehouse = open_warehouse(ctx.data_dir)
    replies = [
        reply
        for reply in records(
            warehouse.query("SELECT * FROM silver.stg_mailbox ORDER BY message_id")
        )
        if reply["message_id"] not in done
    ]
    warehouse.close()
    if not replies:
        return {}

    classified = classify_replies(
        [{"id": r["message_id"], "subject": r["subject"], "body": r["body"]} for r in replies]
    )
    counts: dict[str, int] = {}
    for reply in replies:
        result = classified.get(reply["message_id"])
        if result is None:
            continue  # the classifier was unavailable: this reply is tried again tomorrow
        action, cta_id = route(ctx, reply, result)
        counts[action] = counts.get(action, 0) + 1
        ctx.store.insert(
            "mailbox_triage",
            {
                "message_id": reply["message_id"],
                "processed_on": ctx.day,
                "account_id": reply["account_id"],
                "contact_id": reply["addressed_contact_id"],
                "intent": result["intent"],
                "sentiment": result["sentiment"],
                "confidence": result["confidence"],
                "action": action,
                "cta_id": cta_id,
                "details": json.dumps(
                    {
                        k: result[k]
                        for k in (
                            "seats_requested",
                            "edition_mentioned",
                            "return_date",
                            "new_contact",
                        )
                        if result.get(k)
                    }
                ),
            },
        )
    return counts


def route(ctx: DayContext, reply: dict, result: dict) -> tuple[str, str | None]:
    """Decide what to do with one classified reply. Returns (action taken, CTA id if any)."""
    settings = ctx.catalog.routing["mailbox"]
    account = ctx.accounts.get(reply["account_id"])
    contact = _contact(ctx, reply)
    quote = " ".join(reply["body"].split())[:400]

    if account is None:
        return "account_not_active", None

    if result["confidence"] < settings["min_confidence"]:
        cta_id = _cta(
            ctx,
            reply,
            contact,
            "human_review",
            "low",
            "low_confidence",
            "Reply the classifier is not sure about",
            "Read the reply and route it.",
            quote,
        )
        return "human_review", cta_id

    rule = settings["routes"][result["intent"]]
    action = rule["action"]

    if action == "ignore":
        return "ignored", None

    if action == "opt_out":
        # Consent first: this takes effect immediately, before the CRM is updated.
        ctx.store.insert(
            "consent_changes",
            {
                "changed_on": ctx.day,
                "contact_id": reply["addressed_contact_id"],
                "account_id": reply["account_id"],
                "new_status": "opted_out",
                "source": "mailbox_triage",
            },
        )
        ctx.opted_out.add(reply["addressed_contact_id"])
        _end_journeys_for_contact(ctx, reply["addressed_contact_id"], "contact opted out")
        return "opted_out", None

    if action == "mark_contact_gone":
        return _mark_contact_gone(ctx, reply, account, contact, quote)

    # Everything below needs someone to act, so it only makes sense for recent replies.
    age_days = (ctx.today - date.fromisoformat(reply["received_date"][:10])).days
    if age_days > rule.get("act_within_days", 9999):
        return f"missed_{result['intent']}", None

    if action == "review":
        cta_id = _cta(
            ctx,
            reply,
            contact,
            "human_review",
            "low",
            "low_confidence",
            "Reply that fits no category",
            "Read the reply and route it.",
            quote,
        )
        return "human_review", cta_id

    if action == "agent_or_cta":
        return _answer_or_hand_off(ctx, reply, account, contact)

    # action == "cta"
    brief = None
    if rule.get("with_brief"):
        trigger = {
            "play_id": "mailbox",
            "trigger_signal": result["intent"],
            "trigger_evidence": quote,
        }
        brief = write_brief(ctx, account, trigger)
    title = {
        "buying_intent": "Buying intent in a reply to our email",
        "complaint": "Complaint in a reply to our email",
        "meeting_request": "Customer asked for a meeting",
    }[result["intent"]]
    next_step = {
        "buying_intent": "Reply today. The customer asked first; the brief has the numbers.",
        "complaint": "Call the customer. Emails to this account are paused until this is resolved.",
        "meeting_request": "Send a booking link or propose two times.",
    }[result["intent"]]
    cta_id = _cta(
        ctx,
        reply,
        contact,
        rule["queue"],
        rule["priority"],
        result["intent"],
        title,
        next_step,
        quote,
        brief,
    )
    if rule.get("pause_account"):
        ctx.store.execute(
            "DELETE FROM paused_accounts WHERE account_id = :id", id=reply["account_id"]
        )
        ctx.store.insert(
            "paused_accounts",
            {
                "account_id": reply["account_id"],
                "reason": "complaint",
                "paused_on": ctx.day,
                "cta_id": cta_id,
            },
        )
        ctx.paused.add(reply["account_id"])
    return f"cta_{result['intent']}", cta_id


def _answer_or_hand_off(ctx, reply, account, contact) -> tuple[str, str | None]:
    """A product question: the onboarding agent answers if it can, otherwise a person does."""
    conversation = converse(account, scripted([reply["body"]]))
    cta_id = None
    if conversation.outcome == "escalated":
        cta_id = hand_off(ctx, conversation, account, contact)
    record_conversation(ctx, conversation, account, contact, None, "mailbox_question", cta_id)
    return ("agent_answered" if cta_id is None else "agent_handed_off"), cta_id


def _mark_contact_gone(ctx, reply, account, contact, quote) -> tuple[str, str | None]:
    """The contact has left. If that leaves no admin we can email, open a research task."""
    contact_id = reply["addressed_contact_id"]
    if contact_id not in ctx.left_company:
        ctx.store.insert(
            "contact_flags",
            {
                "contact_id": contact_id,
                "account_id": reply["account_id"],
                "flag": "left_company",
                "flagged_on": ctx.day,
                "source": "mailbox_triage",
            },
        )
        ctx.left_company.add(contact_id)
    _end_journeys_for_contact(ctx, contact_id, "contact left the company")

    has_admin = consent.emailable_contacts(ctx, reply["account_id"], admins_only=True)
    already_open = ctx.store.one(
        "SELECT cta_id FROM ctas WHERE account_id = :id AND reason_code = 'no_valid_admin' "
        "AND status <> 'resolved'",
        id=reply["account_id"],
    )
    if has_admin or already_open:
        return "contact_marked_gone", None
    cta_id = _cta(
        ctx,
        reply,
        contact,
        "admin_research",
        "low",
        "no_valid_admin",
        "The only admin we could email has left",
        "Identify the new admin, confirm consent, update the CRM.",
        quote,
    )
    return "contact_gone_no_admin_left", cta_id


def _end_journeys_for_contact(ctx: DayContext, contact_id: str, reason: str) -> None:
    ctx.store.execute(
        "UPDATE enrollments SET status = 'exited', exit_reason = :reason, closed_on = :day "
        "WHERE contact_id = :contact AND status = 'active'",
        reason=reason,
        day=ctx.day,
        contact=contact_id,
    )


def _cta(
    ctx, reply, contact, queue, priority, reason_code, title, next_step, quote, brief=None
) -> str:
    return create_cta(
        ctx,
        reply["account_id"],
        queue=queue,
        priority=priority,
        reason_code=reason_code,
        title=title,
        next_step=next_step,
        source="mailbox",
        contact=contact,
        customer_quote=quote,
        brief=brief,
    )


def _contact(ctx: DayContext, reply: dict) -> dict | None:
    people = ctx.contacts.get(reply["account_id"], [])
    return next((c for c in people if c["contact_id"] == reply["addressed_contact_id"]), None)
