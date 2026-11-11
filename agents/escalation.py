"""When the agent must stop and hand off to a human. Hard rules, in code.

Synthetic data, fictional company. See docs/decisions/0003-hard-coded-escalation.md.

A prompt can ask a model to escalate pricing questions. A prompt cannot guarantee
it. These rules run in ordinary code, before and after the model speaks, and
the model cannot talk its way around them:

  1. The customer asks for a person.
  2. The customer is frustrated (classifier score at or above the threshold).
  3. Pricing, contract, refund or legal: always a human. Pricing and upgrades go to Sales.
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
    r"\bcan\s+(someone|somebody)\s+(call|contact|help)\b",
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
    """Rules 1, 2, 3 and 6: must this customer message go to a human?"""
    signals = signals or MessageSignals()

    if ASKS_FOR_PERSON.search(text) or signals.asks_for_human:
        return Escalation(
            "customer_asked_for_person", "pooled_csm", "The customer asked for a person."
        )

    if CONTRACT_OR_LEGAL.search(text) or signals.topic in ("contract", "refund", "legal"):
        return Escalation(
            "pricing_contract_legal",
            "pooled_csm",
            "Contract, refund, billing or legal question: always handled by a person.",
        )
    if PRICING.search(text) or signals.topic == "pricing":
        return Escalation(
            "pricing_contract_legal",
            "sales",
            "Pricing or upgrade question: goes to the account owner.",
        )

    if FRUSTRATED.search(text) or signals.frustration >= FRUSTRATION_THRESHOLD:
        return Escalation("frustration", "pooled_csm", "The customer is frustrated.")

    if any(same_question(text, previous) for previous in earlier):
        return Escalation(
            "repeated_question", "pooled_csm", "The customer asked the same thing twice."
        )
    return None


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
