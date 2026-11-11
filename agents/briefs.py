"""The account-owner brief: what Sales gets with an expansion or upgrade CTA.

Synthetic data, fictional company.

A brief answers five questions for the account owner: what fired, what is the
evidence, what does the customer probably need, how could I open the
conversation, and what could go wrong. It uses only the account's own data.

This file holds the template version: every sentence is built directly from a
field of the gold table, so it cannot invent a fact. Phase 5 adds an LLM-written
version on top, checked against the same fields, with this one as the fallback
whenever the LLM is offline or fails the check.
"""

from __future__ import annotations

from engine.channels import NEXT_EDITION


def brief_facts(account: dict, enrollment: dict) -> dict:
    """The facts a brief may use. Nothing outside this dictionary may appear in a brief."""
    return {
        "account_name": account["account_name"],
        "segment": account["segment"],
        "edition": account["edition"],
        "next_edition": NEXT_EDITION.get(account["edition"], "Enterprise").lower(),
        "arr": account["arr"],
        "seats_licensed": account["seats_licensed"],
        "seats_assigned": account["seats_assigned"],
        "seats_assigned_30_days_ago": account["seats_assigned_30d_ago"],
        "seat_utilisation_pct": round(100 * account["seat_utilisation"]),
        "monthly_active_users": account["mau_30d"],
        "automation_rules": account["automation_rules_total"],
        "automation_rule_limit": account["automation_rule_limit"],
        "integrations": account["integrations_total"],
        "integration_limit": account["integration_limit"],
        "assist_credits_used_30d": int(account["assist_credits_30d"] or 0),
        "assist_credits_included": int(account["assist_credits_included"] or 0),
        "health_score": account["health_score"],
        "health_band": account["health_band"],
        "open_high_priority_tickets": account["open_high_priority_tickets"],
        "latest_nps_score": account["latest_nps_score"],
        "days_to_renewal": account["days_to_renewal"],
        "trigger_signal": enrollment["trigger_signal"],
        "trigger_evidence": enrollment["trigger_evidence"],
        "expansion_score_pct": round(100 * (account["expansion_score"] or 0)),
        "expansion_reasons": account["expansion_top_reasons"],
    }


def write_brief(ctx, account: dict, enrollment: dict) -> str:
    """A short brief for the account owner, built from the account's data only."""
    facts = brief_facts(account, enrollment)
    seats_before = facts["seats_assigned_30_days_ago"]
    trend = ""
    if seats_before is not None and facts["seats_assigned"] > seats_before:
        trend = f" (up from {seats_before} thirty days ago)"

    evidence = [
        f"{facts['seats_assigned']} of {facts['seats_licensed']} seats assigned{trend}, "
        f"{facts['seat_utilisation_pct']}% utilisation.",
        f"{facts['monthly_active_users']} monthly active users.",
    ]
    if facts["automation_rules"] >= facts["automation_rule_limit"]:
        evidence.append(
            f"At the automation rule limit of the {facts['edition']} edition "
            f"({facts['automation_rule_limit']} rules)."
        )
    if facts["assist_credits_included"] and facts["assist_credits_used_30d"]:
        evidence.append(
            f"Used {facts['assist_credits_used_30d']} of {facts['assist_credits_included']} "
            "included Assist credits in the last 30 days."
        )

    # What they probably need follows from the evidence, not from the name of the play.
    out_of_seats = facts["seat_utilisation_pct"] >= 85
    if out_of_seats and enrollment["play_id"] != "edition_upgrade":
        need = "Likely need: more seats for a team that is still growing."
        opener = (
            "Suggested opener: \"Your team has nearly filled its seats. Are more people "
            "joining soon? I can make sure they are not blocked.\""
        )
    else:
        need = f"Likely need: the {facts['next_edition']} edition, which lifts the limit they hit."
        opener = (
            "Suggested opener: \"I noticed your team is getting close to the limits of your "
            "current plan. Would it help to walk through what the next edition changes?\""
        )

    risks = []
    if facts["open_high_priority_tickets"]:
        risks.append(f"{facts['open_high_priority_tickets']} high-priority tickets are open")
    if facts["latest_nps_score"] is not None and facts["latest_nps_score"] <= 6:
        risks.append(f"their latest NPS score was {facts['latest_nps_score']}")
    if facts["health_band"] != "green":
        risks.append(f"health is {facts['health_band']} ({facts['health_score']})")
    if facts["days_to_renewal"] <= 90:
        risks.append(f"renewal is in {facts['days_to_renewal']} days")
    risk_line = "Risks: " + ("; ".join(risks) if risks else "none visible in the data") + "."

    return "\n".join(
        [
            f"Brief for {facts['account_name']} ({facts['segment']}, {facts['edition']} edition, "
            f"ARR ${facts['arr']:,})",
            f"Signal: {facts['trigger_signal']}. {facts['trigger_evidence']}.",
            "Evidence: " + " ".join(evidence),
            need,
            opener,
            risk_line,
            "(Template brief: every figure comes from the account's own data.)",
        ]
    )
