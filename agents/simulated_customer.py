"""The simulated customer admin who talks to the onboarding agent during `run-day`.

Synthetic data, fictional company. This file belongs to the simulation, not to
the agent: it decides whether an admin takes up the offer of a conversation and
what they say. In the live demo a person types instead.

What the admin says is scripted (no LLM call), so a simulated day is cheap and
identical every time. The mix of situations covers what a real inbox would
throw at an onboarding agent: mostly setup questions, and now and then a
pricing question, a request for a person, an upset customer, a vague message or
a question the help centre does not answer.
"""

from __future__ import annotations

from common.config import load_yaml
from engine.assignment import bucket

# What the admin asks, depending on the first setup step they are missing.
QUESTION_FOR_MISSING_STEP = {
    "has_first_board": "Hi, I got your email. What should I do first? I haven't set up any boards yet.",
    "has_five_users": "How do I invite my whole team at once? There are about a dozen of us.",
    "has_integration": "How do I connect our calendar so due dates show up there?",
    "has_sso": "Where do I set up single sign-on? Our IT team is asking.",
}

# (share of conversations, name, messages). The first message of a "setup" scenario is
# replaced by the question for the account's first missing step.
SCENARIOS = [
    (0.55, "setup_question", ["<setup question>", "Thanks, that helps."]),
    (0.15, "pricing_follow_up", ["<setup question>", "Thanks. By the way, how much would it cost to add 10 more seats?"]),
    (0.08, "asks_for_person", ["Can I just talk to someone? I don't have time to read documentation."]),
    (0.07, "frustrated", ["Honestly I'm fed up. We've been trying to get this working for two weeks and nothing works."]),
    (0.08, "vague", ["It doesn't work.", "Sorry: the invitation emails. My colleagues never received them."]),
    (0.07, "not_in_docs", ["Does Relay support time tracking and timesheets?"]),
]  # fmt: skip


def takes_up_the_offer(enrollment_id: str) -> bool:
    """Not every admin responds to the offer of a conversation."""
    uptake = load_yaml("sim_effects.yaml")["agent_conversation_uptake"]
    return bucket(enrollment_id, "agent_uptake") < uptake


def script_for(enrollment_id: str, account: dict) -> tuple[str, list[str]]:
    """Which situation this admin is in, and what they will say. Same account, same script."""
    position, running_total = bucket(enrollment_id, "agent_scenario"), 0.0
    name, messages = SCENARIOS[-1][1], SCENARIOS[-1][2]
    for share, scenario, lines in SCENARIOS:
        running_total += share
        if position < running_total:
            name, messages = scenario, lines
            break

    missing = [column for column in QUESTION_FOR_MISSING_STEP if not account[column]]
    setup_question = QUESTION_FOR_MISSING_STEP[missing[0]] if missing else (
        "How do automation rules work with recurring cards?"
    )
    return name, [setup_question if line == "<setup question>" else line for line in messages]
