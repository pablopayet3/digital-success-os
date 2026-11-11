"""Everything customers do outside the product: tickets, NPS, emails and replies.

Synthetic data, fictional company. As in behavior.py, the numbers are
assumptions; the hidden traits decide who complains, who opens email and who
asks for more seats.
"""

from __future__ import annotations

from datetime import timedelta

from synth import text
from synth.behavior import SETUP_STEPS, seat_utilisation
from synth.util import at_time, clamp, pick, weighted_pick

# Lifecycle emails that were already being sent before the pilot.
CAMPAIGN_SUBJECTS = {
    "onboarding_welcome": "Welcome to Relay: your first three steps",
    "onboarding_tips_1": "Invite your team to Relay Boards",
    "onboarding_tips_2": "Connect your tools: integrations and SSO",
    "monthly_newsletter": "Relay monthly: what is new",
    "product_update": "New in Relay Assist: smarter summaries",
    "webinar_invite": "Live session: automation rules in 30 minutes",
}
ONBOARDING_EMAILS = {0: "onboarding_welcome", 3: "onboarding_tips_1", 7: "onboarding_tips_2"}

TICKET_CATEGORY_WEIGHTS = {
    "how_to": 0.22, "bug": 0.16, "integrations": 0.13, "user_management": 0.12,
    "automation": 0.10, "performance": 0.09, "billing": 0.08, "setup_sso": 0.06,
    "assist_credits": 0.04,
}  # fmt: skip
# A missing setup step makes tickets about that step more likely.
CATEGORY_FOR_MISSING_STEP = {
    "sso_configured": "setup_sso",
    "integration_connected": "integrations",
    "users_invited": "user_management",
    "board_created": "how_to",
}
PRIORITY_NORMAL = {"low": 0.30, "normal": 0.50, "high": 0.17, "urgent": 0.03}
PRIORITY_IN_FRICTION = {"normal": 0.25, "high": 0.55, "urgent": 0.20}


def simulate_account_interactions(world, account, today, rng) -> None:
    """Tickets, NPS and onboarding emails for one account on one day."""
    age = (today - account.contract_start).days
    _maybe_ticket(world, account, today, age, rng)
    _maybe_nps(world, account, today, age, rng)

    if age in ONBOARDING_EMAILS:
        for contact in account.contacts:
            if contact.persona == "admin":
                send_email(world, account, contact, ONBOARDING_EMAILS[age], today, rng)

    # Now and then someone leaves the company. The CRM is not told.
    if rng.random() < 0.001:
        pick(rng, account.contacts).has_left = True


def send_campaign_emails(world, today, rng) -> None:
    """Emails that go to many accounts on the same day."""
    campaigns = []
    if today.day == 5:
        campaigns.append(("monthly_newsletter", None))
    if today.day == 18:
        campaigns.append(("webinar_invite", ("admin", "champion")))
    if world.day_index % 45 == 20:
        campaigns.append(("product_update", None))

    for campaign, personas in campaigns:
        for account in world.accounts:
            if account.contract_start > today or account.status != "active":
                continue
            for contact in account.contacts:
                if personas is None or contact.persona in personas:
                    send_email(world, account, contact, campaign, today, rng)


# --- Support tickets ---------------------------------------------------------------------


def _maybe_ticket(world, account, today, age: int, rng) -> None:
    in_friction = account.friction_days_left > 0
    chance = 0.006 + 0.012 * (1 - account.fit)
    if age < 30:
        chance += 0.02 * (1 - account.setup_drive)  # new admins who struggle ask for help
    chance *= 1 + account.seats_assigned / 100  # bigger teams raise more tickets
    if in_friction:
        chance += 0.30
    if rng.random() >= chance:
        return

    missing_steps = [step for step in SETUP_STEPS if step not in account.setup_done]
    if missing_steps and age < 45 and rng.random() < 0.6:
        category = CATEGORY_FOR_MISSING_STEP[pick(rng, missing_steps)]
    else:
        category = weighted_pick(rng, TICKET_CATEGORY_WEIGHTS)
    priority = weighted_pick(rng, PRIORITY_IN_FRICTION if in_friction else PRIORITY_NORMAL)
    serious = priority in ("high", "urgent")
    angry = bool(rng.random() < 0.05 + 0.45 * in_friction + 0.3 * (1 - account.fit) * serious)

    admins = [c for c in account.contacts if c.persona == "admin"]
    requester = pick(rng, admins) if admins and rng.random() < 0.7 else pick(rng, account.contacts)
    subject, body = text.make_ticket(rng, category, angry, requester.full_name.split()[0])
    created_at = at_time(today, rng, 7, 19)
    days_to_resolve = rng.exponential(5.0 if in_friction else 2.0)

    ticket_id = world.next_id("T")
    world.tickets.append(
        {
            "ticket_id": ticket_id,
            "account_id": account.account_id,
            "contact_id": requester.contact_id,
            "created_at": created_at,
            "priority": priority,
            "category": category,
            "subject": subject,
            "body": body,
            # Not exported as-is: status and resolved_at are worked out when files are written.
            "resolves_at": created_at + timedelta(days=float(days_to_resolve)),
            "waiting_status": "pending" if rng.random() < 0.3 else "open",
        }
    )
    world.ticket_labels.append({"ticket_id": ticket_id, "tone": "angry" if angry else "calm"})


# --- NPS surveys -------------------------------------------------------------------------


def _maybe_nps(world, account, today, age: int, rng) -> None:
    """Roughly every 45 days an account is surveyed; one or two people may answer."""
    if age < 14 or rng.random() >= 1 / 45:
        return
    reachable = [c for c in account.contacts if c.email_valid and not c.has_left]
    if not reachable:
        return
    in_friction = account.friction_days_left > 0
    for _ in range(int(rng.integers(1, 3))):
        contact = pick(rng, reachable)
        if rng.random() >= 0.25 + 0.35 * account.engagement:
            continue  # no answer
        happiness = 0.33 + 0.5 * account.fit + 0.3 * min(account.momentum, 1.0)
        happiness += rng.normal(0, 0.13) - (0.25 if in_friction else 0.0)
        score = round(10 * clamp(happiness, 0.0, 1.0))
        responded_at = at_time(today, rng, 8, 20)
        world.nps.append(
            {
                "response_id": world.next_id("N"),
                "account_id": account.account_id,
                "contact_id": contact.contact_id,
                "score": score,
                "comment": text.make_nps_comment(rng, score),
                "responded_at": responded_at,
            }
        )
        contact.last_engaged_at = responded_at


# --- Emails and the replies they trigger -------------------------------------------------


def send_email(world, account, contact, campaign: str, today, rng, subject: str | None = None):
    """Send one email and decide what the recipient does with it.

    Returns the row recorded for the email, or None when it may not be sent.
    Emails from plays pass their own subject; lifecycle campaigns use the fixed ones.
    """
    is_onboarding = campaign.startswith("onboarding")
    if contact.consent_status == "opted_out":
        return None
    if not is_onboarding and contact.consent_status != "opted_in":
        return None  # marketing email needs explicit consent; onboarding email is transactional

    sent_at = at_time(today, rng, 13, 15)
    send = {
        "send_id": world.next_id("S"),
        "campaign": campaign,
        "subject": subject or CAMPAIGN_SUBJECTS[campaign],
        "contact_id": contact.contact_id,
        "account_id": account.account_id,
        "sent_at": sent_at,
        "delivered": True,
        "bounced": False,
        "opened_at": None,
        "clicked_at": None,
        "unsubscribed": False,
    }
    world.email_sends.append(send)

    if not contact.email_valid:
        send["delivered"], send["bounced"] = False, True
        return send
    if contact.has_left:
        # Delivered to a mailbox nobody reads. Sometimes an auto-reply says so.
        if rng.random() < 0.05:
            _add_reply(world, account, contact, send, "left_company", sent_at, rng)
        return send
    if rng.random() < 0.0025:
        _add_reply(world, account, contact, send, "out_of_office", sent_at, rng)

    opened = rng.random() < 0.10 + 0.55 * contact.affinity * min(account.momentum, 1.0)
    if not opened:
        return send
    opened_at = sent_at + timedelta(minutes=int(rng.integers(2, 480)))
    send["opened_at"] = opened_at
    contact.last_engaged_at = opened_at
    if rng.random() < 0.08 + 0.4 * contact.affinity:
        send["clicked_at"] = opened_at + timedelta(minutes=int(rng.integers(1, 20)))
        contact.last_engaged_at = send["clicked_at"]
    if not is_onboarding and rng.random() < 0.006:
        send["unsubscribed"] = True  # used the unsubscribe link: consent is updated properly
        contact.consent_status = "opted_out"
        return send

    if rng.random() < 0.04 * world.cfg["volumes"]["mailbox_reply_scale"]:
        _add_reply(world, account, contact, send, _reply_intent(account, rng), opened_at, rng)
    return send


def _reply_intent(account, rng) -> str:
    """What a human reply is about depends on the state of the account."""
    wants_more = seat_utilisation(account) >= 0.8
    unhappy = account.momentum < 0.6 or account.friction_days_left > 0
    return weighted_pick(
        rng,
        {
            "product_question": 0.30,
            "meeting_request": 0.16,
            "unsubscribe": 0.14,
            "buying_intent": 0.10 + 0.35 * account.growth * wants_more,
            "complaint": 0.08 + 0.45 * (1 - account.fit) * unhappy,
        },
    )


def _add_reply(world, account, contact, send: dict, intent: str, after, rng) -> None:
    """A reply lands in the shared success mailbox.

    Nobody was reading that mailbox before the pilot. So a contact who replied
    "unsubscribe" is still opted in, and a contact who left is still listed as
    valid. Fixing that is the job of the mailbox triage agent (Phase 5).
    """
    others = [c for c in account.contacts if c is not contact]
    colleague = pick(rng, others) if others else contact
    reply = text.make_reply(
        rng,
        intent,
        {
            "name": contact.full_name,
            "first": contact.full_name.split()[0],
            "company": account.name,
            "role": contact.role,
            "colleague": colleague.full_name,
            "subject": send["subject"],
            "sent_day": send["sent_at"].strftime("%d %b %Y"),
        },
    )

    # Most replies come from the person we emailed. A colleague answers for someone who
    # left, and now and then a person replies from a different address.
    from_email, from_name = contact.email, contact.full_name
    if intent == "left_company" and reply["is_hard"]:
        from_email, from_name = colleague.email, colleague.full_name
    elif intent not in text.AUTOMATIC and rng.random() < 0.05:
        from_email = contact.email.replace("@", ".mobile@")

    received_at = after + timedelta(minutes=int(rng.integers(1, 45)))
    message_id = world.next_id("M")
    world.mailbox.append(
        {
            "message_id": message_id,
            "received_at": received_at,
            "from_email": from_email,
            "from_name": from_name,
            "to_email": text.SUCCESS_MAILBOX,
            "in_reply_to": send["send_id"],
            "subject": reply["subject"],
            "body": reply["body"],
        }
    )
    world.mailbox_labels.append(
        {
            "message_id": message_id,
            "intent": reply["intent"],
            "sentiment": reply["sentiment"],
            "secondary_intent": reply["secondary_intent"],
            "is_hard": reply["is_hard"],
            "account_id": account.account_id,
            "contact_id": contact.contact_id,
        }
    )
    if intent not in text.AUTOMATIC:
        contact.last_engaged_at = received_at
