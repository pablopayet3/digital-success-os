"""When the agent must stop and hand off to a human. Hard rules, in code.

Synthetic data, fictional company. See docs/decisions/0003-hard-coded-escalation.md.

A prompt can ask a model to escalate pricing questions. A prompt cannot guarantee
it. These rules run in ordinary code, before and after the model speaks, and
the model cannot talk its way around them:

  1. The customer asks for a person.
  2. The customer is frustrated (classifier score at or above the threshold).
  3. Pricing, contract, refund or legal: always a human. Pricing and upgrades go to Sales.
  3b. Something is broken (an error, a bug, a crash): Support owns faults, so it goes there.
  4. The docs do not cover the question. (One clarifying question is allowed first.)
  5. A tool fails or times out. Hand off; never guess.
  6. The same question comes back a second time.
  7. The model itself is unavailable, refuses, or asks to hand off.

Rules 1 to 3 use two detectors on every customer message: plain keyword patterns,
which always work, and an LLM classifier, which catches what keywords miss
("this is the last straw"). Either one is enough to escalate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from agents.retrieval import tokens

FRUSTRATION_THRESHOLD = 0.7

ASKS_FOR_PERSON = re.compile(
    r"\b(talk|speak|chat)\s+(to|with)\s+(a\s+|an\s+|the\s+)?(human|person|someone|somebody|agent|"
    r"representative|rep|manager)\b|\b(real|actual)\s+(human|person)\b|\bcall\s+me\b|"
    r"\b(can|could)\s+(someone|somebody)\s+(call|contact|help)\b",
    re.IGNORECASE,
)
PRICING = re.compile(
    r"\b(pric(e|es|ing)|cost|costs|quote|discount|how much|upgrade|more seats|extra seats|"
    r"add seats|buy|purchase|package|plan change)\b",
    re.IGNORECASE,
)
CONTRACT_OR_LEGAL = re.compile(
    r"\b(contract|refund|refunds|invoice|billing|charged|cancel|cancellation|terminate|legal|"
    r"lawyer|liability|gdpr|dpa|data processing|terms of service|renewal terms)\b",
    re.IGNORECASE,
)
# A fault, not a how-to question. "It doesn't work" is left out on purpose: it is usually
# a vague setup question, and the agent asks one clarifying question first.
PRODUCT_FAULT = re.compile(
    r"\b(error|errors|bug|bugs|crash|crashes|crashed|crashing|broken|stopped working|outage)\b",
    re.IGNORECASE,
)
FRUSTRATED = re.compile(
    r"\b(fed up|unacceptable|ridiculous|useless|worst|waste of (time|money)|furious|angry|"
    r"third time|sick of|terrible|cancel(l)?ing)\b",
    re.IGNORECASE,
)


@dataclass
class MessageSignals:
    """What the classifier says about one customer message (agents/classify.py)."""

    asks_for_human: bool = False
    frustration: float = 0.0
    topic: str = "product"  # setup | product | pricing | contract | refund | legal | other
    confidence: float = 1.0


@dataclass
class Escalation:
    reason_code: str  # one of the reason codes in config/routing.yaml
    queue: str
    why: str  # one sentence for the human who picks it up


def check_message(
    text: str, signals: MessageSignals | None, earlier: list[str]
) -> Escalation | None:
    """Rules 1, 2, 3 and 6: must this customer message go to a human? The first reason found."""
    found = check_message_all(text, signals, earlier)
    return found[0] if found else None


def check_message_all(
    text: str, signals: MessageSignals | None, earlier: list[str]
) -> list[Escalation]:
    """Every team this message needs, most important first, one handoff per team.

    "How much are 10 more seats? And could someone help us set up single sign-on?" asks for
    two things: a price, which only Sales gives, and a person for setup help, which is the
    Customer Success team's job. Each need gets one owner, in that owner's queue.
    """
    signals = signals or MessageSignals()
    found: list[Escalation] = []

    def add(escalation: Escalation) -> None:
        if all(earlier_one.queue != escalation.queue for earlier_one in found):
            found.append(escalation)

    if ASKS_FOR_PERSON.search(text) or signals.asks_for_human:
        add(
            Escalation(
                "customer_asked_for_person", "pooled_csm", "The customer asked for a person."
            )
        )
    if CONTRACT_OR_LEGAL.search(text) or signals.topic in ("contract", "refund", "legal"):
        add(
            Escalation(
                "pricing_contract_legal",
                "pooled_csm",
                "Contract, refund, billing or legal question: always handled by a person.",
            )
        )
    if PRICING.search(text) or signals.topic == "pricing":
        add(
            Escalation(
                "pricing_contract_legal",
                "sales",
                "Pricing or upgrade question: goes to the account owner.",
            )
        )
    if PRODUCT_FAULT.search(text):
        add(
            Escalation(
                "product_fault",
                "support",
                "The customer reports something broken: Support owns faults.",
            )
        )
    if FRUSTRATED.search(text) or signals.frustration >= FRUSTRATION_THRESHOLD:
        add(Escalation("frustration", "pooled_csm", "The customer is frustrated."))
    if any(same_question(text, previous) for previous in earlier):
        add(
            Escalation(
                "repeated_question", "pooled_csm", "The customer asked the same thing twice."
            )
        )
    return found


def check_retrieval(
    covered: bool | None, reply: str, clarifications_so_far: int
) -> Escalation | None:
    """Rule 4: the model searched the docs and no article covers the question.

    One thing is still allowed: asking the customer a single clarifying question.
    Answering anyway is not. That would be guessing.
    """
    if covered is None or covered:
        return None  # nothing was searched, or an article covers the question
    asks_to_clarify = reply.rstrip().endswith("?")
    if asks_to_clarify and clarifications_so_far == 0:
        return None
    return Escalation("not_in_docs", "pooled_csm", "The help centre does not cover this question.")


def same_question(a: str, b: str) -> bool:
    """True when two messages share most of their meaningful words."""
    words_a, words_b = set(tokens(a)), set(tokens(b))
    if len(words_a) < 3 or len(words_b) < 3:
        return False
    return len(words_a & words_b) / len(words_a | words_b) >= 0.7


# --- What the customer is told when a person takes over (a warm handoff) --------------------

NUMBERS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}
SINGLE_SIGN_ON = re.compile(r"single sign-on|\bsso\b", re.IGNORECASE)


def _within(queue: dict) -> str:
    """The team's promised reply time in words: 48 hours becomes "two days"."""
    days = -(-queue["sla_hours"] // 24)  # rounded up
    return f"{NUMBERS.get(days, days)} day" + ("" if days == 1 else "s")


def _promise(escalation: Escalation, queues: dict, quote: str) -> str:
    """One sentence per team: who will contact the customer, about what, and by when."""
    within = _within(queues[escalation.queue])
    if escalation.queue == "sales":
        return f"Your account owner on our Sales team will email you about pricing within {within}."
    if escalation.queue == "pooled_csm":
        topic = (
            "to set up single sign-on with you" if SINGLE_SIGN_ON.search(quote) else "to help you"
        )
        return f"Someone from our Customer Success team will contact you within {within} {topic}."
    if escalation.queue == "support":
        return f"Our Support team will look into it and reply within {within}."
    return f"Our {queues[escalation.queue]['name']} will reply within {within}."


def warm_transfer(escalations: list[Escalation], queues: dict, quote: str = "") -> str:
    """The agent's last message when people take over: who, about what, by when, and that
    the customer will not have to repeat themselves. Written by a rule, the same every time."""
    promises = " ".join(_promise(escalation, queues, quote) for escalation in escalations)
    if len(escalations) == 1:
        opening, everyone = "I've passed this to a person who can help.", "They can"
    else:
        opening = f"Those go to {NUMBERS.get(len(escalations), 'several')} people who can help."
        everyone = "Both can" if len(escalations) == 2 else "They can all"
    return (
        f"{opening} {promises} {everyone} see this conversation, so you won't need to repeat "
        "anything."
    )
