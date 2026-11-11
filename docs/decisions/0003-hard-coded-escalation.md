# 0003: Escalation rules in code, not only in the prompt

Status: accepted (Phase 5). Synthetic data, fictional company.

## Context

An onboarding agent talks to customers who have no account manager. Some things it must
never do: quote a price, discuss a contract, argue with an upset customer, or answer a
product question from memory. A wrong price is a promise the company has to keep.

A prompt can ask a model not to do these things. A prompt cannot guarantee it. Models
follow instructions most of the time, and "most of the time" is not a control.

## Options

1. Prompt only. Simple, flexible, and unverifiable.
2. **Rules in code around the model, plus the prompt.** The rules decide; the prompt makes
   the model behave well inside them.
3. A second model that reviews every reply. Catches more, doubles the cost and latency,
   and is still a model.

## Decision

Option 2. `agents/escalation.py` holds seven rules. Each maps to a reason code and a queue.

Before the agent model is called, every customer message is checked for: a request for a
person; frustration; pricing or upgrade (to Sales); contract, refund, billing or legal;
and the same question asked twice. If a rule fires, the conversation is handed off and
the agent model is never asked. Two detectors feed these rules, and either is enough:

- keyword patterns, which need no model and always run;
- a small classifier model, which catches what keywords miss ("this is the last straw").

After the agent's turn, three more checks: a tool failed or timed out; the model was
unavailable, declined, or asked to hand off; or the model replied although no help article
covers the question. One clarifying question is allowed; an answer is not.

The tools are also bound to the account in the conversation. They take no account id, so
the model cannot be talked into looking up another customer.

## Consequences

- The behaviours that matter most can be tested without a model. `tests/test_agents.py`
  checks each rule, and checks that a pricing message never reaches the agent model.
- Keyword rules over-escalate. "How much storage do we get?" contains "how much" and goes
  to Sales. That is the right direction to be wrong in: a person answers a question the
  agent could have answered. The outcome `agent_should_have_handled` measures how often.
- The prompt still matters: it decides how good the answers are and how gracefully the
  agent hands off. It no longer carries the safety case alone.
- New rules are a code change, reviewed through change control.

## Revisit if

The unnecessary-handoff rate from keyword rules is high enough to waste the team's time.
Then narrow the patterns using the logged cases, rather than removing the rule.
