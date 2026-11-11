# Prompt changelog

Synthetic data, fictional company. Prompts are versioned like code: a new version is a
new file, the old one stays, and this file says what changed and why. The version in use
is set in `config/llm.yaml` (`prompt_versions`). Evals compare versions on the same cases
(`evals/`, Phase 6) before a new one becomes the default.

## onboarding_agent

### v2 (current)

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

## brief, judge, customer_simulator

### v1 (current)

First versions.
