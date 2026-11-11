# Evaluation report

Synthetic data, fictional company. Written by `uv run python run.py evals`.

- **Answers produced by:** stand-in (keyword rules, not an LLM)
- **Agent prompt in use:** v2
- **Models in config:** agent `claude-opus-5-5`, classifier and judge `claude-haiku-5-5`
- **Cost of this run:** LLM mode: stand-in (keyword rules, not an LLM). 182 stand-in answers, no API calls, $0 spent.

> **Read this first.** These results come from the rule-based stand-in, not from a
> language model. They show that the code around the model works: the escalation
> rules, the tools, retrieval, routing and the number check on briefs. They say
> nothing about how well a real model answers, and the two prompt versions cannot
> differ because the stand-in does not read the prompt. Cases that need language
> understanding are skipped. Run once with an API key to replace this report.

## Summary

| Suite | Cases run | Passed | Failed | Skipped | Pass rate |
|---|---|---|---|---|---|
| onboarding agent (v1) | 27 | 27 | 0 | 3 | 100% |
| onboarding agent (v2) | 27 | 27 | 0 | 3 | 100% |
| mailbox cases | 9 | 9 | 0 | 1 | 100% |
| briefs | 4 | 4 | 0 | 0 | 100% |

## Onboarding agent: prompt versions compared

The same cases, run with each prompt version. Pass rate by category.

| Category | Cases | v1 | v2 |
|---|---|---|---|
| contract | 3 | 3 of 3 | 3 of 3 |
| edition | 2 | 0 of 0 | 0 of 0 |
| failure | 1 | 1 of 1 | 1 of 1 |
| frustration | 2 | 2 of 2 | 2 of 2 |
| not_in_docs | 3 | 3 of 3 | 3 of 3 |
| person | 2 | 2 of 2 | 2 of 2 |
| pricing | 3 | 3 of 3 | 3 of 3 |
| repeated | 1 | 1 of 1 | 1 of 1 |
| safety | 1 | 1 of 1 | 1 of 1 |
| setup | 11 | 10 of 10 | 10 of 10 |
| vague | 1 | 1 of 1 | 1 of 1 |

Cases whose result changed between v1 and v2:

- None.

## Failures

None.

## Skipped

- `mbx-09-sarcastic-complaint`: needs a real language model
- `onb-11-is-sso-in-my-edition`: needs a real language model; the stand-in cannot pass it
- `onb-12-what-premium-includes`: needs a real language model; the stand-in cannot pass it
- `onb-30-french`: needs a real language model; the stand-in cannot pass it

## Mailbox classifier: hand-written cases

| Case | Result | Classified as -> action |
|---|---|---|
| `mbx-01-out-of-office-german` | passed | out_of_office (0.90) -> ignore |
| `mbx-02-unsubscribe-polite` | passed | unsubscribe (0.90) -> opt_out |
| `mbx-03-complaint-outranks-unsubscribe` | passed | complaint (0.90) -> cta |
| `mbx-04-left-company` | passed | left_company (0.90) -> mark_contact_gone |
| `mbx-05-buying-outranks-question` | passed | buying_intent (0.90) -> cta |
| `mbx-06-meeting` | passed | meeting_request (0.90) -> cta |
| `mbx-07-product-question` | passed | product_question (0.90) -> agent_or_cta |
| `mbx-08-too-short-to-tell` | passed | other (0.40) -> review |
| `mbx-09-sarcastic-complaint` | skipped | needs a real language model |
| `mbx-10-on-leave-not-gone` | passed | out_of_office (0.90) -> ignore |

## Mailbox classifier: accuracy against the simulator's labels

160 replies, evenly sampled. Accuracy **97%** (plain replies 100%, deliberately hard ones 89%).

| Intent | Replies | Precision | Recall |
|---|---|---|---|
| buying_intent | 21 | 100% | 100% |
| complaint | 20 | 100% | 100% |
| left_company | 20 | 100% | 100% |
| meeting_request | 27 | 100% | 100% |
| other | 0 | 0% | n/a |
| out_of_office | 20 | 100% | 75% |
| product_question | 35 | 100% | 100% |
| unsubscribe | 17 | 100% | 100% |

Confusion matrix (rows: what it was; columns: what the classifier said).

| | buying_intent | complaint | left_company | meeting_request | other | out_of_office | product_question | unsubscribe |
|---|---|---|---|---|---|---|---|---|
| **buying_intent** | 21 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **complaint** | 0 | 20 | 0 | 0 | 0 | 0 | 0 | 0 |
| **left_company** | 0 | 0 | 20 | 0 | 0 | 0 | 0 | 0 |
| **meeting_request** | 0 | 0 | 0 | 27 | 0 | 0 | 0 | 0 |
| **out_of_office** | 0 | 0 | 0 | 0 | 5 | 15 | 0 | 0 |
| **product_question** | 0 | 0 | 0 | 0 | 0 | 0 | 35 | 0 |
| **unsubscribe** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 17 |

Costly misses (an unsubscribe or a complaint read as something else): **0**.

## Account briefs

| Case | Result | Brief used |
|---|---|---|
| `brf-01-seats-nearly-full` | passed | AI-written |
| `brf-02-at-the-rule-limit` | passed | AI-written |
| `brf-03-growing-but-unhappy` | passed | AI-written |
| `brf-04-renewal-is-close` | passed | AI-written |

## How to read this

- A case passes only when every check written in code passes. The judge is asked only
  about answers that already passed those checks, and scores wording and grounding.
- A new prompt version becomes the default only when it does not lose a case the old
  one passed in the hard-rule categories (pricing, contract, person, frustration).
- Handoffs that people close as "the agent should have handled this" become new cases
  under `evals/cases/from_feedback/`.
