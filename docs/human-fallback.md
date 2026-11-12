# Human fallback: how digital and agentic work hands off to people

Synthetic data, fictional company. One page on the design: when a handoff happens, what
travels with it, where it goes, what comes back, and how the agent improves from it.

The principle: **an agent that cannot help must fail safely and visibly.** It hands off
with everything a person needs, and the person's outcome flows back into the system.

## 1. When

A handoff happens in three ways.

**A journey reaches its human rung.** Every play declares an intervention ladder (digital,
agentic, human) and the rule for moving up. Example, onboarding rescue: an email; if still
stalled after 3 days, the agent; if the agent escalates or the account is still stalled 4
days later, a person.

**A hard rule fires during an agent conversation.** These rules are code, not prompt
(`agents/escalation.py`). The model cannot talk its way around them.

| # | Rule | Goes to |
|---|---|---|
| 1 | The customer asks for a person | Scaled CS team |
| 2 | The customer is frustrated (keywords, or classifier score at 0.7 or above) | Scaled CS team |
| 3 | Pricing or upgrade question | Sales |
| 3 | Contract, refund, billing or legal question | Scaled CS team |
| 4 | The help centre does not cover the question (one clarifying question allowed) | Scaled CS team |
| 5 | A tool fails or times out. Hand off, never guess | Scaled CS team |
| 6 | The same question comes back a second time | Scaled CS team |
| 7 | The model is unavailable, declines, or asks to hand off | Scaled CS team |

Rules 1 to 3 run before the agent model is called at all: a pricing question never
reaches it. Two detectors check every message, keyword patterns and a small classifier
model, and either one is enough. If the classifier is down, the keywords still work.

**The mailbox triage agent routes a reply to a person** (`agents/mailbox.py`): a complaint,
buying intent, a meeting request, or anything the classifier is not sure about.

## 2. What travels: the handoff packet

Every handoff is a CTA carrying a typed packet (`engine/handoff.py`, `HandoffPacket`).
The test for the packet: can the person act without asking the customer to repeat anything?

| Field | Why it is there |
|---|---|
| Account and contact (name, email, role) | Who to call |
| Trigger (play, signal, evidence, every signal firing) | Why now |
| Reason code | Why a person, in one of 16 countable codes |
| Conversation summary | What the customer wanted and what the agent already said |
| What was tried | Every touch this journey already delivered, with dates |
| Customer quote | Their own words: the message that triggered the handoff, or their NPS comment |
| Account snapshot | Health score and its five components, seats, edition, renewal date, open tickets, churn and expansion scores with reasons |
| Recommended next step | One sentence |
| Brief (Sales CTAs) | Signal, evidence, likely need, suggested opener, risks |
| Priority, queue, SLA due date | How urgent, whose, by when |

## 3. Where it goes

`config/routing.yaml` defines five queues, each with an SLA and a daily capacity: scaled
CS team (48 hours), account owners (72), support (24), contact research (120), mailbox
review (48). Within a queue, work is ordered by priority, then by SLA. When a queue holds
more than two days of work, an alert is raised and stored.

The journey waits. An account with an open handoff is not sent further automated touches
by that play, and a complaint or a missing admin pauses every play's emails for the account.

## 4. What comes back: the return signal

A person closes the CTA with an outcome and a note. The outcome decides what happens next:

| Outcome | What happens to the journey |
|---|---|
| `resolved` | Re-enters the journey at the step after the handoff |
| `saved` | Re-enters the journey |
| `expansion_opportunity` | Sales owns it from here; the journey completes |
| `not_a_fit` | Exits |
| `no_response` | Exits |
| `agent_should_have_handled` | Re-enters the journey, and the case goes to the evaluation queue |

Without a return signal a handoff is a dead end: the journey never knows whether to
continue, and nobody learns which handoffs were unnecessary.

## 5. How the agent improves

- **Unnecessary handoffs become test cases.** `agent_should_have_handled` puts the
  conversation in the evaluation review queue; from the Human console it is also written
  to `evals/cases/from_feedback/` as a draft case. The next prompt version has to pass it.
- **So does a thumbs down.** Anyone reading a conversation on the Agents page can rate
  it. A thumbs down, with a note on what should have happened, puts the conversation in
  the same review queue (`agents/review.py`). The queue is a tab on the Agents page.
- **Missing knowledge becomes a docs gap list.** Handoffs with reason `not_in_docs` are
  counted by question. The most frequent ones are the next help articles to write.
- **Every conversation is traced** (`agents/tracing.py`): messages, tool calls, retrieved
  articles, decision, cost, latency, with names and email addresses masked.

## 6. How we know it works

| Metric | Definition |
|---|---|
| Handoff rate | Agent conversations that ended in a handoff, divided by all agent conversations |
| Time to pickup | Days from CTA created to picked up |
| SLA breach rate | CTAs picked up after their SLA due date, divided by all CTAs |
| Escalation conversion | Handoffs closed as resolved, saved or expansion opportunity, divided by handoffs closed |
| Unnecessary handoff rate | Handoffs closed as `agent_should_have_handled`, divided by handoffs closed |
| Docs gap share | Handoffs with reason `not_in_docs`, divided by agent handoffs |
| Re-contact after handoff | Accounts with a new handoff within 14 days of one being closed |

These are computed in the warehouse from the operational tables (Phase 6) and shown in
the app (Phase 7).
