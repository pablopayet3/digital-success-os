# Prompt changelog

Synthetic data, fictional company. Prompts are versioned like code: a new version is a
new file, the old one stays, and this file says what changed and why. The version in use
is set in `config/llm.yaml` (`prompt_versions`). Evals compare versions on the same cases
(`evals/`, Phase 6) before a new one becomes the default.

## onboarding_agent

### v3 (current)

Written after the first live evaluation, which v2 lost to v1. Two changes from v2:

1. **The answer must be written as text, every time.** With v2 the model sometimes
   logged the outcome and then told the admin "I've shown you how to create your first
   board" without the steps ever appearing. It had worked the answer out and behaved
   as if it had been sent. v3 says plainly that the admin sees only the text.
2. **State only what a tool result says.** v2's "check setup status first" led the model
   to add friendly inferences ("connecting the calendar completes your integration
   step") that no tool result or article supports. The judge failed them as ungrounded.

Result on the 30 agent cases with the real model: v1 29, v2 25, v3 30. v3 became the
default (`config/llm.yaml`). One caution: v3 was written after seeing where v1 and v2
failed on these same cases, so 30 of 30 is a result on cases it was tuned against. New
cases, from real handoffs, are what will show whether it holds.

### v2 (not promoted)

The evaluation did not confirm the expected effect below: v2 passed 25 of 30 where v1
passed 29. It is kept as written, as the record of what was tried.

Changes from v1, each with its reason:

1. **Says who the customer is and why they are here** (a busy admin of a stalled, uncovered
   account). v1 gave the model a role but no situation, so it had nothing to calibrate tone
   and length against.
2. **Tells the agent to check setup status first.** Without it the agent can answer a
   question about a step the account has already completed.
3. **Answers only from the help centre, and names the article.** v1 said "search the help
   centre" but did not forbid answering from memory. The reason is stated in the prompt:
   an invented step costs the admin more time than no answer.
4. **One clarifying question for vague messages.** v1 would search on "it doesn't work" and
   answer whatever came back.
5. **Separates "what an edition includes" from "what it costs".** v1 said to hand off
   pricing questions, which also blocked harmless questions such as "is SSO in my
   edition?". v2 lets the agent explain features and reserves prices and changes for people.
6. **Says how to hand off**: one sentence to the admin, and a summary written for a
   colleague who has not seen the conversation.
7. **Adds frustration and "not in the help centre" as hand-off reasons.**

The hard escalation rules in `agents/escalation.py` apply to both versions. The prompt
makes the agent hand off gracefully; the code makes sure it happens.

Expected effect, to be confirmed by the prompt A/B in `evals/reports/`: higher pass rate
on the vague-question, not-in-docs and edition-feature cases; fewer unnecessary handoffs
on feature questions; no change on the hard-rule cases.

### v1

The first version: role, tools, and a one-line hand-off rule. Kept as the baseline for
the A/B comparison.

## classifier_message, classifier_mailbox, classifier_feedback

### v1 (current)

Short instructions plus a JSON schema the reply must match. No examples: the categories
are few and their names are plain. Add examples only for categories the eval shows are
confused with each other.

## judge

### v2 (current)

The judge is now given the account facts the agent's tools returned, and told the agent
may state them. v1 saw only the help articles, so on the first live run it marked
correct statements such as "4 of your 15 seats are assigned" as invented and failed
good answers. A judge has to see what the agent saw.

### v1

Articles only.

## brief, customer_simulator

### v1 (current)

First versions.
