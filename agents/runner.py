"""Connects the onboarding agent to the journey runner.

Synthetic data, fictional company. When a journey reaches an `agent` step, the
engine calls `run_onboarding_step`. This module:

  1. plays the customer (simulated here; a person in the live demo),
  2. runs the conversation (agents/onboarding.py),
  3. turns an escalation into a handoff with a full packet (engine/handoff.py),
  4. stores the conversation and writes a masked trace.

It registers itself with the engine when imported, so the engine never has to
know which agent it is talking to.
"""

from __future__ import annotations

import json

from agents.briefs import brief_facts, template_brief
from agents.escalation import SINGLE_SIGN_ON
from agents.llm import get_llm
from agents.onboarding import Conversation, _default_next_step, converse, scripted
from agents.simulated_customer import script_for, takes_up_the_offer
from agents.tracing import Trace
from engine import channels
from engine.channels import AgentResult
from engine.context import DayContext
from engine.handoff import create_cta

_conversations_this_run = 0


def run_onboarding_step(
    ctx: DayContext, enrollment: dict, step, account: dict, contact: dict
) -> AgentResult:
    """Run the agent step of a journey for one account."""
    global _conversations_this_run
    if not takes_up_the_offer(enrollment["enrollment_id"]):
        return AgentResult("no_uptake", "The admin did not take up the offer of a conversation.")

    cap = get_llm().settings.max_agent_conversations_per_run
    if _conversations_this_run >= cap:
        return AgentResult(
            "unavailable", f"Agent conversation cap for this run ({cap}) reached.",
            reason_code="agent_unavailable",
        )  # fmt: skip
    _conversations_this_run += 1

    scenario, lines = script_for(enrollment["enrollment_id"], account)
    conversation = converse(account, scripted(lines))
    cta_id = None
    if conversation.outcome == "escalated":
        cta_id = hand_off(ctx, conversation, account, contact, enrollment, step.id)
    record_conversation(ctx, conversation, account, contact, enrollment, scenario, cta_id)

    if conversation.outcome == "escalated":
        return AgentResult(
            "escalated", conversation.summary, conversation.escalation.reason_code,
            conversation.customer_quote, cta_id,
        )  # fmt: skip
    return AgentResult("resolved", conversation.summary)


def hand_off(
    ctx,
    conversation: Conversation,
    account,
    contact,
    enrollment=None,
    step_id=None,
    escalation=None,
) -> str:
    """Create the CTA for an escalated conversation. Returns the CTA id.

    `escalation` picks one of the teams when a message needed more than one
    (`conversation.more_escalations`); by default, the main one.
    """
    escalation = escalation or conversation.escalation
    urgent = escalation.reason_code in ("frustration", "customer_asked_for_person")
    brief = None
    if escalation.queue == "sales":  # Sales always gets the account-owner brief
        quote = (conversation.customer_quote or escalation.why).rstrip(" .?!")
        trigger = {
            "play_id": enrollment["play_id"] if enrollment else "agent",
            "trigger_signal": "pricing question to the agent",
            "trigger_evidence": f'The customer asked: "{quote}"',
        }
        # Built from the account's facts, without a model call: the customer is waiting on
        # the page, and a template cannot invent a number (agents/briefs.py).
        brief = template_brief(brief_facts(account, trigger), trigger)
    return create_cta(
        ctx,
        account["account_id"],
        queue=escalation.queue,
        priority="high" if urgent else "normal",
        reason_code=escalation.reason_code,
        title=f"Agent handoff: {escalation.why}",
        next_step=(
            conversation.recommended_next_step
            if escalation is conversation.escalation
            else _default_next_step(escalation)
        ),
        source="agent",
        enrollment=enrollment,
        step_id=step_id,
        contact=contact,
        # The summary opens with why this team has it: each team its own reason.
        conversation_summary=conversation.summary.replace(
            conversation.escalation.why, escalation.why, 1
        ),
        customer_quote=conversation.customer_quote,
        brief=brief,
        draft_reply=draft_reply(escalation, contact, conversation.customer_quote or ""),
    )


def draft_reply(escalation, contact, quote: str) -> str:
    """A first reply to the customer, for the person who takes over to check, edit and send.

    Written from a template, not by a model: it never quotes a price or promises anything
    only the person can decide. The person stays the one who sends it.
    """
    name = contact["full_name"].split()[0] if contact else "there"
    if escalation.queue == "sales":
        about = "more seats" if "seat" in quote.lower() else "pricing"
        body = (
            f"Thanks for asking about {about}. I'll send you the price for your plan today. "
            "Would a 15-minute call this week help, to make sure it fits what your team needs?"
        )
    elif escalation.queue == "pooled_csm":
        task = (
            "set up single sign-on with you"
            if SINGLE_SIGN_ON.search(quote)
            else "help you finish setting up Relay"
        )
        body = f"I'm happy to {task}. Does Thursday at 10:00 work for a 30-minute call?"
    elif escalation.queue == "support":
        body = (
            "Thanks for reporting this. I'm looking into it now and will update you within a day."
        )
    else:
        body = "Thanks for your message. I'm looking into it and will get back to you shortly."
    return f"Hi {name},\n\n{body}\n\nBest regards"


def record_conversation(
    ctx, conversation: Conversation, account, contact, enrollment, scenario, cta_id
) -> str:
    """Store the conversation and write its trace. Returns the conversation id."""
    names = [contact["full_name"], contact["full_name"].split()[0]] if contact else []
    trace = Trace("onboarding_agent", account["account_id"], ctx.day, names)
    for turn in conversation.transcript:
        trace.step(turn["role"], text=turn["text"])
    for call in conversation.tool_calls:
        trace.step("tool_call", tool=call["name"], input=call["input"])
    for search in conversation.searches:
        trace.step("retrieval", query=search["query"], results=search["results"])
    reason = conversation.escalation.reason_code if conversation.escalation else None
    folder = ctx.data_dir / "traces"
    trace_path = trace.finish(conversation.outcome, reason, conversation.llm_log, folder)

    # Which model wrote the agent's replies. Recorded per conversation, so a stored answer
    # is never mistaken for another model's (a real model's, or the rule-based stand-in's).
    models = sorted({call["model"] for call in conversation.llm_log if call["role"] == "agent"})
    answered_by = ", ".join(models) or "no agent model: a hard rule stopped it first"

    conversation_id = ctx.store.next_id("conversations", "CNV")
    ctx.store.insert(
        "conversations",
        {
            "conversation_id": conversation_id,
            "day": ctx.day,
            "account_id": account["account_id"],
            "contact_id": contact["contact_id"] if contact else None,
            "play_id": enrollment["play_id"] if enrollment else None,
            "enrollment_id": enrollment["enrollment_id"] if enrollment else None,
            "scenario": scenario,
            "prompt_version": conversation.prompt_version,
            "outcome": conversation.outcome,
            "reason_code": reason,
            "escalated_by": conversation.escalated_by,
            "queue": conversation.escalation.queue if conversation.escalation else None,
            "customer_turns": sum(1 for t in conversation.transcript if t["role"] == "customer"),
            "transcript": json.dumps(conversation.transcript),
            "tool_calls": json.dumps(conversation.tool_calls),
            "searches": json.dumps(conversation.searches),
            "llm_calls": len(conversation.llm_log),
            "cached_llm_calls": sum(1 for call in conversation.llm_log if call["cached"]),
            "cost_usd": round(sum(call["cost_usd"] for call in conversation.llm_log), 6),
            "latency_ms": sum(call["latency_ms"] for call in conversation.llm_log),
            "trace_file": trace_path.name,
            "cta_id": cta_id,
            "feedback": None,
            "answered_by": answered_by,
        },
    )
    return conversation_id


channels.register_agent_runner(run_onboarding_step)
