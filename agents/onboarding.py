"""The onboarding agent: one conversation with a customer admin.

Synthetic data, fictional company.

`converse()` runs a whole conversation and returns what happened. It has no side
effects: it does not create CTAs or write to any database. The caller decides
what to do with the result (the journey runner creates a handoff, the evals
score it, the live demo shows it). That keeps one agent behind every use.

Each customer message goes through the same steps:

  1. Read it.     A small model classifies it; keyword patterns check it too.
  2. Hard rules.  If the customer asks for a person, is upset, or asks about pricing,
                  contracts, refunds or legal matters, the conversation is handed off
                  now. The agent model is not asked. (agents/escalation.py)
  3. Agent turn.  The model answers, calling tools as it needs: setup status, account
                  context, help-centre search.
  4. Checks.      A failed tool, a model that is unavailable or declines, a reply written
                  when no article covers the question: each one is a handoff.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from agents.classify import classify_message
from agents.escalation import Escalation, check_message, check_retrieval
from agents.llm import LLMUnavailable, get_llm
from agents.tools import HANDOFF_REASONS, TOOL_DEFINITIONS, AgentTools, ToolFailure
from common.config import load_yaml
from common.paths import ROOT

MAX_TOOL_ROUNDS = 6  # tool calls the model may chain in one turn before we call it stuck
MAX_CUSTOMER_TURNS = 4


@dataclass
class Conversation:
    outcome: str = "resolved"  # resolved | escalated
    escalation: Escalation | None = None
    summary: str = ""  # for the human who picks up a handoff
    recommended_next_step: str = ""
    customer_quote: str | None = None  # the message that triggered a handoff
    transcript: list = field(default_factory=list)  # [{"role": "customer" | "agent", "text"}]
    tool_calls: list = field(default_factory=list)  # [{"name", "input"}]
    searches: list = field(default_factory=list)  # every help-centre search and its results
    escalated_by: str | None = None  # "hard_rule" | "agent" | "failure"
    prompt_version: str = ""
    llm_log: list = field(default_factory=list)


def system_prompt(version: str | None = None) -> tuple[str, str]:
    """The agent's instructions. Returns (text, version)."""
    version = version or load_yaml("llm.yaml")["prompt_versions"]["onboarding_agent"]
    path = ROOT / "prompts" / "onboarding_agent" / f"{version}.md"
    return path.read_text(encoding="utf-8"), version


def converse(
    account: dict,
    next_message: Callable[[list], str | None],
    prompt_version: str | None = None,
    failing_tool: str | None = None,
) -> Conversation:
    """Run one conversation.

    `next_message(transcript)` plays the customer: it returns their next message, or
    None when they have nothing more to say. `failing_tool` simulates a tool that is
    down (used by tests and evals).
    """
    llm = get_llm()
    log_start = len(llm.log)
    system, version = system_prompt(prompt_version)
    tools = AgentTools(account, failing_tool)
    result = Conversation(prompt_version=version)
    messages: list[dict] = []  # the conversation as the model sees it
    earlier_questions: list[str] = []
    clarifications = 0

    def hand_off(
        escalation: Escalation, by: str, quote: str | None, summary: str = "", next_step: str = ""
    ) -> Conversation:
        result.outcome, result.escalation, result.escalated_by = "escalated", escalation, by
        result.customer_quote = quote
        result.summary = summary or _summary(result, tools, escalation)
        result.recommended_next_step = next_step or _default_next_step(escalation)
        return _finish(result, tools, llm, log_start)

    for _ in range(MAX_CUSTOMER_TURNS):
        customer_text = next_message(result.transcript)
        if customer_text is None:
            break
        result.transcript.append({"role": "customer", "text": customer_text})

        # Steps 1 and 2: read the message and apply the hard rules before the agent speaks.
        escalation = check_message(
            customer_text, classify_message(customer_text), earlier_questions
        )
        if escalation:
            return hand_off(escalation, "hard_rule", customer_text)
        earlier_questions.append(customer_text)

        # Step 3: the agent's turn.
        messages.append({"role": "user", "content": customer_text})
        searches_before = len(tools.searches)
        try:
            reply = _agent_turn(llm, system, messages, tools, result)
        except ToolFailure as failure:
            # A tool failed or timed out: hand off. The agent never guesses.
            return hand_off(
                Escalation("tool_failure", "pooled_csm", f"A tool failed: {failure}"),
                "failure",
                customer_text,
            )
        except LLMUnavailable as unavailable:
            return hand_off(
                Escalation(
                    "agent_unavailable", "pooled_csm", f"The agent could not run: {unavailable}"
                ),
                "failure",
                customer_text,
            )

        # Step 4: checks after the turn.
        if tools.handoff:  # the model itself asked for a human
            reason = tools.handoff["reason"]
            escalation = Escalation(reason, HANDOFF_REASONS[reason], "The agent handed off.")
            if reply:
                result.transcript.append({"role": "agent", "text": reply})
            return hand_off(
                escalation,
                "agent",
                customer_text,
                tools.handoff["summary"],
                tools.handoff["recommended_next_step"],
            )
        searched_this_turn = len(tools.searches) > searches_before
        covered = tools.docs_cover_question if searched_this_turn else None
        escalation = check_retrieval(covered, reply, clarifications)
        if escalation:
            return hand_off(escalation, "hard_rule", customer_text)
        if covered is False:
            clarifications += 1  # the one clarifying question that is allowed
        result.transcript.append({"role": "agent", "text": reply})

    return _finish(result, tools, llm, log_start)


def _agent_turn(llm, system: str, messages: list, tools: AgentTools, result: Conversation) -> str:
    """Let the model answer one customer message, running the tools it asks for."""
    for _ in range(MAX_TOOL_ROUNDS):
        response = llm.call(
            "agent", system, messages, tools=TOOL_DEFINITIONS, purpose="onboarding agent turn"
        )
        if response.stop_reason == "refusal":
            raise LLMUnavailable("the model declined to answer")
        # The model's reply goes back into the conversation exactly as it came.
        messages.append({"role": "assistant", "content": response.content})
        if not response.tool_calls:
            return response.text

        tool_results = []
        for call in response.tool_calls:
            result.tool_calls.append({"name": call["name"], "input": call["input"]})
            output = tools.run(call["name"], call["input"])  # may raise ToolFailure
            tool_results.append(
                {"type": "tool_result", "tool_use_id": call["id"], "content": output}
            )
        messages.append({"role": "user", "content": tool_results})
        if tools.handoff:
            return response.text  # the model handed off: the conversation ends here
    raise ToolFailure("the agent kept calling tools without answering")


def _finish(result: Conversation, tools: AgentTools, llm, log_start: int) -> Conversation:
    result.searches = tools.searches
    result.llm_log = llm.log[log_start:]
    if result.outcome == "resolved" and not result.summary:
        answered = sum(1 for turn in result.transcript if turn["role"] == "agent")
        result.summary = f"The agent answered {answered} message(s) from the admin."
    return result


def _summary(result: Conversation, tools: AgentTools, escalation: Escalation) -> str:
    """A handoff summary written by code, for when a rule stops the conversation."""
    account = tools.account
    said = [turn["text"] for turn in result.transcript if turn["role"] == "customer"]
    answered = sum(1 for turn in result.transcript if turn["role"] == "agent")
    missing = ", ".join(tools.setup_status()["missing_steps"]) or "nothing"
    return (
        f'{escalation.why} The admin of {account["account_name"]} wrote: "{said[-1]}" '
        f"The agent had answered {answered} earlier message(s). "
        f"Setup still missing: {missing}."
    )


def _default_next_step(escalation: Escalation) -> str:
    if escalation.queue == "sales":
        return "Reply to the admin about pricing or the upgrade; they asked the agent directly."
    if escalation.reason_code == "frustration":
        return "Call the admin. Acknowledge the frustration before anything else."
    return "Contact the admin and pick up where the agent stopped; the transcript is attached."


def scripted(messages: list[str]) -> Callable[[list], str | None]:
    """A customer who says a fixed list of things, one per turn."""
    queue = list(messages)
    return lambda transcript: queue.pop(0) if queue else None
