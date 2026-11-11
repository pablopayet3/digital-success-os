"""Text classification with the small model: intent, sentiment, confidence.

Synthetic data, fictional company.

Three jobs, one pattern (a short instruction, a JSON schema the reply must match,
the small cheap model):

  classify_message   one customer message inside an agent conversation: does it
                     ask for a person, how frustrated is it, what is it about?
  classify_replies   replies in the shared mailbox: one of eight intents, sentiment,
                     confidence, and the useful details (seats asked for, return date).
  classify_feedback  NPS comments and ticket texts: sentiment and theme.

Texts are classified in small batches (several per call) and only once: identical
texts share a result, and every call is cached by agents/llm.py.
The classifier advises; it never acts. What happens next is decided by plain
rules (agents/escalation.py, agents/mailbox.py).
"""

from __future__ import annotations

import json

from agents.escalation import MessageSignals
from agents.llm import LLMUnavailable, get_llm
from common.paths import ROOT

PROMPT_DIR = ROOT / "prompts"
BATCH_SIZE = 8

MAILBOX_INTENTS = [
    "out_of_office", "unsubscribe", "left_company", "product_question",
    "buying_intent", "complaint", "meeting_request", "other",
]  # fmt: skip
SENTIMENTS = ["positive", "neutral", "negative"]

MESSAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "asks_for_human": {"type": "boolean"},
        "frustration": {"type": "number"},
        "topic": {
            "type": "string",
            "enum": ["setup", "product", "pricing", "contract", "refund", "legal", "other"],
        },
        "confidence": {"type": "number"},
    },
    "required": ["asks_for_human", "frustration", "topic", "confidence"],
    "additionalProperties": False,
}

REPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "intent": {"type": "string", "enum": MAILBOX_INTENTS},
                    "sentiment": {"type": "string", "enum": SENTIMENTS},
                    "confidence": {"type": "number"},
                    "seats_requested": {"type": "string"},
                    "edition_mentioned": {"type": "string"},
                    "return_date": {"type": "string"},
                    "new_contact": {"type": "string"},
                },
                "required": [
                    "id", "intent", "sentiment", "confidence", "seats_requested",
                    "edition_mentioned", "return_date", "new_contact",
                ],  # fmt: skip
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}

FEEDBACK_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "sentiment": {"type": "string", "enum": SENTIMENTS},
                    "theme": {
                        "type": "string",
                        "enum": ["setup", "usability", "performance", "support", "pricing",
                                 "value", "other"],
                    },  # fmt: skip
                    "confidence": {"type": "number"},
                },
                "required": ["id", "sentiment", "theme", "confidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}


def prompt(name: str) -> str:
    return (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")


def classify_message(text: str) -> MessageSignals | None:
    """Read one customer message. Returns None when the classifier is unavailable.

    The caller still applies its keyword rules, so an unavailable classifier
    makes escalation less sensitive, never impossible.
    """
    try:
        response = get_llm().call(
            "classifier",
            prompt("classifier_message"),
            [{"role": "user", "content": text}],
            json_schema=MESSAGE_SCHEMA,
            purpose="classify customer message",
        )
        return MessageSignals(**json.loads(response.text))
    except (LLMUnavailable, ValueError, TypeError):
        return None


def classify_replies(replies: list[dict]) -> dict[str, dict]:
    """Classify mailbox replies. `replies` are {"id", "subject", "body"}. Returns {id: result}."""
    return _classify_in_batches(replies, "classifier_mailbox", REPLY_SCHEMA, "classify mailbox")


def classify_feedback(texts: list[dict]) -> dict[str, dict]:
    """Classify NPS comments and ticket texts. `texts` are {"id", "text"}. Returns {id: result}."""
    return _classify_in_batches(texts, "classifier_feedback", FEEDBACK_SCHEMA, "classify feedback")


def _classify_in_batches(items: list[dict], prompt_name: str, schema: dict, purpose: str) -> dict:
    """Send the items a few at a time. Stops quietly when the LLM becomes unavailable."""
    results: dict[str, dict] = {}
    for start in range(0, len(items), BATCH_SIZE):
        batch = items[start : start + BATCH_SIZE]
        try:
            response = get_llm().call(
                "classifier",
                prompt(prompt_name),
                [{"role": "user", "content": json.dumps(batch, ensure_ascii=False)}],
                json_schema=schema,
                purpose=purpose,
            )
            for result in json.loads(response.text)["results"]:
                results[result["id"]] = result
        except LLMUnavailable:
            break  # offline with no cache, or the budget is spent: classify the rest later
        except (ValueError, KeyError):
            continue  # an unreadable reply for this batch; the others may still work
    return results
