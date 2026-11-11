"""How simulated customers react to the touches the engine delivered.

Synthetic data, fictional company.

This is where the treatment effects live. Each morning the world receives the
touches from the day before (emails, in-app prompts, agent conversations, human
follow-ups) and applies what config/sim_effects.yaml says they do. Everything
here is an assumption, stated in that file
(docs/decisions/0005-simulated-treatment-effects.md).

An email only has an effect if the simulated contact opens it. Opens, clicks
and replies to journey emails are recorded exactly like any other email, so they
flow through the pipeline and show up in the gold tables.
"""

from __future__ import annotations

from common.config import load_yaml
from synth import interactions
from synth.accounts import Contact
from synth.util import pick

GOOD_HUMAN_OUTCOMES = {"resolved", "saved", "expansion_opportunity"}
FIRST_NAMES = ["Alex", "Sam", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Jamie"]
LAST_NAMES = ["Rivera", "Okafor", "Lindqvist", "Tanaka", "Moreau", "Novak", "Haddad", "Sorensen"]


def apply_interventions(world, interventions: dict, today, rng) -> None:
    """Apply yesterday's touches. `interventions` maps account id to a list of touches."""
    effects_by_play = load_yaml("sim_effects.yaml")["effects"]
    for account_id, touches in interventions.items():
        account = world.account(account_id)
        if account is None or account.status != "active":
            continue
        for touch in touches:
            effects = effects_by_play.get(touch["play_id"], {})
            kind = touch["kind"]
            if kind == "email":
                contact = _contact(account, touch.get("contact_id"))
                if contact is None:
                    continue
                send = interactions.send_email(
                    world, account, contact, f"play_{touch['play_id']}", today, rng,
                    subject=touch.get("subject") or "A message from the Relay team",
                )  # fmt: skip
                if send and send["opened_at"]:
                    _apply(world, account, effects.get("email_opened"), rng)
            elif kind == "in_app":
                _apply(world, account, effects.get("in_app"), rng)
            elif kind == "agent" and touch.get("outcome") == "resolved":
                _apply(world, account, effects.get("agent_resolved"), rng)
            elif kind == "human" and touch.get("outcome") in GOOD_HUMAN_OUTCOMES:
                _apply(world, account, effects.get("human_resolved"), rng)


def _apply(world, account, effect: dict | None, rng) -> None:
    for name, value in (effect or {}).items():
        if name == "setback_relief":
            account.setback *= 1 - value
        elif name == "momentum":
            account.momentum = min(1.25, account.momentum + value)
        elif name == "new_admin":
            _add_admin(world, account, rng)
        else:
            # setup_help, expansion_x, upgrade_x, docs_trial: kept on the account and
            # faded a little every day by behavior.simulate_account_day
            account.help[name] = max(account.help.get(name, 0.0), value)


def _add_admin(world, account, rng) -> None:
    """The research task found the right person: a reachable admin joins the CRM."""
    first, last = pick(rng, FIRST_NAMES), pick(rng, LAST_NAMES)
    contact_id = world.next_id("C")
    account.contacts.append(
        Contact(
            contact_id=contact_id,
            account_id=account.account_id,
            full_name=f"{first} {last}",
            email=f"{first}.{last}.{contact_id[-4:]}@{account.domain}".lower(),
            persona="admin",
            role="Workspace Admin",
            consent_status="opted_in",
            email_valid=True,
            product_user_id=None,
            last_engaged_at=None,
            affinity=0.6,
            has_left=False,
        )
    )


def _contact(account, contact_id: str | None):
    return next((c for c in account.contacts if c.contact_id == contact_id), None)
