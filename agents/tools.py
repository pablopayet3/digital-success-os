"""The tools the onboarding agent can call.

Synthetic data, fictional company.

A tool is a function the model may ask us to run. The model sees the name, the
description and the inputs; our code does the work and returns the result.

Two design choices:

  - The tools are bound to one account: the one in the conversation. They take no
    account id, so the model cannot look up anyone else's data, whatever it is asked.
  - A tool that fails raises ToolFailure. The conversation then hands off to a human.
    The model is never left to guess what the tool would have said.
"""

from __future__ import annotations

import json

from agents.retrieval import knowledge_base
from engine.handoff import SETUP_STEPS, account_snapshot

HANDOFF_REASONS = {
    "customer_asked_for_person": "pooled_csm",
    "pricing_contract_legal": "sales",
    "not_in_docs": "pooled_csm",
    "low_confidence": "pooled_csm",
    "frustration": "pooled_csm",
}

TOOL_DEFINITIONS = [
    {
        "name": "get_account_context",
        "description": (
            "Facts about the customer's account: edition, seats, lifecycle stage, health "
            "score and its components, open tickets, latest NPS score. Call it when the "
            "answer depends on the customer's edition or situation."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_setup_status",
        "description": (
            "Which of the four setup steps the account has completed (first board, five "
            "users, an integration, single sign-on) and which are still missing. Call it "
            "first in an onboarding conversation."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "search_docs",
        "description": (
            "Search the Relay help centre. Returns the best-matching articles with their "
            "full text. Answer product questions only from what this returns."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to look for, in a few words."}
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "create_handoff",
        "description": (
            "Hand the conversation to a human, with a summary. Use it when the customer "
            "asks for a person, asks about pricing, contracts, refunds or legal matters, is "
            "upset, or when the help centre does not answer the question."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "enum": sorted(HANDOFF_REASONS)},
                "summary": {
                    "type": "string",
                    "description": "What the customer wants and what was already tried.",
                },
                "recommended_next_step": {"type": "string"},
            },
            "required": ["reason", "summary", "recommended_next_step"],
            "additionalProperties": False,
        },
    },
    {
        "name": "log_outcome",
        "description": "Record how the conversation ended. Call it once, at the end.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "outcome": {"type": "string", "enum": ["answered", "partly_answered"]},
                "note": {"type": "string", "description": "One sentence on what was resolved."},
            },
            "required": ["outcome", "note"],
            "additionalProperties": False,
        },
    },
]


class ToolFailure(Exception):
    """A tool could not do its job (an error or a timeout)."""


class AgentTools:
    """Runs tool calls for one conversation about one account."""

    def __init__(self, account: dict, failing_tool: str | None = None):
        self.account = account
        self.failing_tool = failing_tool  # tests use this to simulate a tool that is down
        self.searches: list[dict] = []  # every search and what it returned
        self.handoff: dict | None = None  # set when the model asks to hand off
        self.outcome: dict | None = None

    @property
    def docs_cover_question(self) -> bool | None:
        """Did the latest search find an article that covers the question? None if no search."""
        if not self.searches:
            return None
        return any(result["covers_question"] for result in self.searches[-1]["results"])

    def run(self, name: str, arguments: dict) -> str:
        """Run one tool call and return its result as JSON text."""
        if name == self.failing_tool:
            raise ToolFailure(f"{name} timed out")
        try:
            if name == "get_account_context":
                return json.dumps(account_snapshot(self.account))
            if name == "get_setup_status":
                return json.dumps(self.setup_status())
            if name == "search_docs":
                return json.dumps(self._search(arguments["query"]))
            if name == "create_handoff":
                self.handoff = arguments
                return json.dumps({"status": "handed off to a human"})
            if name == "log_outcome":
                self.outcome = arguments
                return json.dumps({"status": "recorded"})
        except ToolFailure:
            raise
        except Exception as error:  # any unexpected failure is treated like a timeout
            raise ToolFailure(f"{name} failed: {error}") from error
        raise ToolFailure(f"unknown tool: {name}")

    def setup_status(self) -> dict:
        done = [label for column, label in SETUP_STEPS.items() if self.account[column]]
        missing = [label for column, label in SETUP_STEPS.items() if not self.account[column]]
        return {
            "completed_steps": done,
            "missing_steps": missing,
            "closure_pct": self.account["prerequisite_closure_pct"],
            "seats_assigned": self.account["seats_assigned"],
            "seats_licensed": self.account["seats_licensed"],
            "edition": self.account["edition"],
        }

    def _search(self, query: str) -> dict:
        results = knowledge_base().search(query)
        kept = ("slug", "title", "score", "coverage", "covers_question")
        self.searches.append(
            {"query": query, "results": [{k: r[k] for k in kept} for r in results]}
        )
        covered = any(result["covers_question"] for result in results)
        note = (
            "At least one article covers this question."
            if covered
            else "No article covers this question. Do not answer from memory: ask one "
            "clarifying question, or hand off."
        )
        return {"query": query, "note": note, "articles": results}
