"""A rule-based stand-in for the LLM. It is NOT a language model.

Synthetic data, fictional company.

Why it exists: the demo must run with no API key, no network and no cost. Offline
mode normally replays real model responses from the cache. Until that cache has
been filled by one live run, this stand-in plays the model's part so the whole
flow can still be shown: tools, retrieval, escalation rules, handoffs, mailbox
routing.

What it is: a few keyword rules. It receives the same request the real API would
and returns a response in the same shape. Everything it produces is labelled
"stand-in" (the model name in every trace and conversation), so nobody can
mistake its output for a real model's.

What it is not: evidence about answer quality. Evaluation reports produced with
the stand-in test the code around the model, not the model.

Switch it on with `llm_stand_in: true` in config/environments.yaml or
DSO_LLM_STAND_IN=true. The tests use it too (tests/fake_llm.py).
"""

from __future__ import annotations

import hashlib
import json
import re

STAND_IN_MODEL = "stand-in (keyword rules, not an LLM)"


def stand_in_transport(request: dict) -> dict:
    """Answer one request the way the real API would be asked to."""
    schema = request.get("json_schema")
    if schema and "asks_for_human" in schema["properties"]:
        return _text(json.dumps(_message_signals(request["messages"][-1]["content"])))
    if schema and "results" in schema["properties"]:
        items = json.loads(request["messages"][-1]["content"])
        item_schema = schema["properties"]["results"]["items"]["properties"]
        classify = _reply if "intent" in item_schema else _feedback
        return _text(json.dumps({"results": [classify(item) for item in items]}))
    if schema and "verdict" in schema["properties"]:
        return _text(json.dumps(_judge(request["messages"][-1]["content"])))
    if "You answer questions about the Digital Success OS" in request["system"]:
        return _assistant(request)
    if request["tools"]:
        return _agent(request)
    if "account owner" in request["system"]:
        return _text(_brief(json.loads(request["messages"][-1]["content"])))
    return _text("OK")


# --- the stand-in for the "Ask the data" assistant ---------------------------------------


def _assistant(request: dict) -> dict:
    """Search the documents for the question, then name what was found. It writes no SQL
    and composes no answer: it is labelled as rules, not a model, wherever it appears."""
    last = request["messages"][-1]["content"]
    if isinstance(last, str):
        if not request["tools"]:
            return _text(_ASSISTANT_NOTE)
        return _tools(request, [("search_docs", {"query": last})])
    found = " ".join(str(block.get("content", "")) for block in last if isinstance(block, dict))
    sources = sorted(set(re.findall(r"\[([^\]]+\.md)\]", found)))[:3]
    if not sources:
        return _text(_ASSISTANT_NOTE)
    return _text(
        f"{_ASSISTANT_NOTE} The documents closest to your question are: {', '.join(sources)}."
    )


_ASSISTANT_NOTE = (
    "This reply comes from the labelled stand-in, which is a set of keyword rules and not "
    "an AI model, so it cannot write an answer from the data."
)


# --- the stand-in agent ------------------------------------------------------------------


def _agent(request: dict) -> dict:
    """First look things up; then answer from the docs, ask to clarify, or hand off."""
    last = request["messages"][-1]["content"]
    new_message = _customer_text(last)
    if new_message is not None:  # a customer message: look things up first
        lookups = [("get_setup_status", {}), ("search_docs", {"query": new_message})]
        return _tools(request, lookups)

    # Tool results came back. Find the search result among them.
    search = None
    for block in last:
        content = json.loads(block["content"])
        if "articles" in content:
            search = content
    customer = _last_customer_message(request["messages"])
    if search and "No article covers" in search["note"]:
        if len(customer.split()) <= 4:  # too vague to search on: ask
            return _text("Could you tell me a bit more about what is not working?")
        handoff = {
            "reason": "not_in_docs",
            "summary": f"The admin asked: {customer} The help centre has no article on it.",
            "recommended_next_step": "Answer the admin's question directly.",
        }
        return _tools(request, [("create_handoff", handoff)])
    if search:
        article = search["articles"][0]
        steps = _first_steps(article.get("text", ""))
        return _text(f"Here is how, from the help article '{article['title']}'. {steps}".strip())
    return _text("A colleague will follow up, and you will not need to repeat yourself.")


def _first_steps(text: str) -> str:
    """The first paragraph of an article after its title, so the answer quotes the docs."""
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    body = [part for part in paragraphs if not part.startswith(("#", "Search keywords"))]
    return body[0] if body else "Follow the steps there."


def _customer_text(content) -> str | None:
    """The customer's words in a message: plain text, or a text block after tool results."""
    if isinstance(content, str):
        return content
    texts = [block["text"] for block in content if block.get("type") == "text"]
    return texts[-1] if texts else None


def _last_customer_message(messages: list[dict]) -> str:
    said = (_customer_text(m["content"]) for m in reversed(messages) if m["role"] == "user")
    return next(text for text in said if text is not None)


# --- the stand-in classifiers ----------------------------------------------------------------


def _message_signals(text: str) -> dict:
    lowered = text.lower()
    topic = "product"
    if any(word in lowered for word in ("cost", "price", "pricing", "seats")):
        topic = "pricing"
    elif any(word in lowered for word in ("refund", "contract", "invoice")):
        topic = "contract"
    return {
        "asks_for_human": "is anyone there" in lowered,
        "frustration": 0.9 if "last straw" in lowered else 0.1,
        "topic": topic,
        "confidence": 0.9,
    }


REPLY_RULES = [
    ("out_of_office", ("out of the office", "automatic reply", "annual leave", "travelling",
                       "absent", "nicht im büro")),
    ("left_company", ("no longer works", "has left", "mailbox is disabled", "undeliverable",
                      "moved on", "i have left")),
    ("complaint", ("not acceptable", "cancelling", "lost a day", "fix that first",
                   "stopped using", "painful")),
    ("unsubscribe", ("unsubscribe", "remove me", "take me off", "stop sending", "stop these")),
    ("buying_intent", ("more seats", "pricing", "what would it cost", "bigger package",
                       "add relay docs", "seat count", "enterprise would give")),
    ("meeting_request", ("call next week", "walk our admins", "book a session", "calendar link",
                         "someone i can talk to")),
    ("product_question", ("how do", "can guests", "is there a way", "where do i", "does relay",
                          "is sso included", "is that normal")),
]  # fmt: skip


def _reply(item: dict) -> dict:
    text = f"{item['subject']} {item['body']}".lower()
    intent = next((name for name, words in REPLY_RULES if any(w in text for w in words)), "other")
    return {
        "id": item["id"],
        "intent": intent,
        "sentiment": "negative" if intent == "complaint" else "neutral",
        "confidence": 0.4 if intent == "other" else 0.9,
        "seats_requested": "",
        "edition_mentioned": "",
        "return_date": "",
        "new_contact": "",
    }


def _feedback(item: dict) -> dict:
    text = item["text"].lower()
    negative = any(w in text for w in ("fed up", "not happy", "cancelling", "disappointed", "poor"))
    return {
        "id": item["id"],
        "sentiment": "negative" if negative else "neutral",
        "theme": "support" if "ticket" in text else "other",
        "confidence": 0.8,
    }


def _brief(facts: dict) -> str:
    return (
        f"Signal: {facts['trigger_signal']}.\n"
        f"Evidence: {facts['seats_assigned']} of {facts['seats_licensed']} seats assigned.\n"
        "Likely need: more seats.\nSuggested opener: Are more people joining soon?\n"
        "Risks: none visible in the data."
    )


def _judge(text: str) -> dict:
    """A stand-in judge can only check the obvious: does the reply point at a help article?"""
    grounded = "help article" in text.lower() or "article '" in text.lower()
    return {
        "verdict": "pass" if grounded else "fail",
        "score": 4 if grounded else 2,
        "reason": "Stand-in judge: checks only that the reply cites a help article.",
    }


# --- response shapes ---------------------------------------------------------------------------


def _text(text: str) -> dict:
    return {
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "model": STAND_IN_MODEL,
        "usage": {"input_tokens": 400, "output_tokens": 60},
    }


def _tools(request: dict, tool_calls: list[tuple[str, dict]]) -> dict:
    # Ids come from the request itself, so they are the same on every run and never clash.
    stem = hashlib.sha256(json.dumps(request, sort_keys=True, default=str).encode()).hexdigest()
    blocks = [
        {"type": "tool_use", "id": f"toolu_{stem[:12]}_{n}", "name": name, "input": arguments}
        for n, (name, arguments) in enumerate(tool_calls)
    ]
    return {
        "content": blocks,
        "stop_reason": "tool_use",
        "model": STAND_IN_MODEL,
        "usage": {"input_tokens": 400, "output_tokens": 40},
    }
