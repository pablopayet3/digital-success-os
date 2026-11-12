# Evaluation report

Synthetic data, fictional company. Written by `uv run python run.py evals`.

- **Answers produced by:** offline (replaying cached model responses)
- **Agent prompt in use:** v3
- **Models in config:** agent `claude-opus-5-5`, classifier and judge `claude-haiku-5-5`
- **Cost of this run:** LLM mode: offline (replaying cached model responses). LLM calls: 334 (334 from cache, 0 paid), spent $0.0000 of $5.00

## Summary

| Suite | Cases run | Passed | Failed | Skipped | Pass rate |
|---|---|---|---|---|---|
| onboarding agent (v1) | 30 | 29 | 1 | 0 | 97% |
| onboarding agent (v2) | 30 | 25 | 5 | 0 | 83% |
| onboarding agent (v3) | 30 | 30 | 0 | 0 | 100% |
| mailbox cases | 10 | 10 | 0 | 0 | 100% |
| briefs | 4 | 4 | 0 | 0 | 100% |

## Onboarding agent: prompt versions compared

The same cases, run with each prompt version. Pass rate by category.

| Category | Cases | v1 | v2 | v3 |
|---|---|---|---|---|
| contract | 3 | 3 of 3 | 3 of 3 | 3 of 3 |
| edition | 2 | 2 of 2 | 1 of 2 | 2 of 2 |
| failure | 1 | 1 of 1 | 1 of 1 | 1 of 1 |
| frustration | 2 | 2 of 2 | 2 of 2 | 2 of 2 |
| not_in_docs | 3 | 3 of 3 | 3 of 3 | 3 of 3 |
| person | 2 | 2 of 2 | 2 of 2 | 2 of 2 |
| pricing | 3 | 3 of 3 | 3 of 3 | 3 of 3 |
| repeated | 1 | 1 of 1 | 1 of 1 | 1 of 1 |
| safety | 1 | 1 of 1 | 1 of 1 | 1 of 1 |
| setup | 11 | 10 of 11 | 7 of 11 | 11 of 11 |
| vague | 1 | 1 of 1 | 1 of 1 | 1 of 1 |

Cases whose result changed between v1 and v3:

- `onb-02-invite-whole-team`: failed with v1, passed with v3

## Failures

- `onb-02-invite-whole-team` (onboarding agent, v1): judge: 3/5: Point 1 (grounded) fails: the reply states as fact that inviting the team finishes the 'invite at least five users' setup step, which appears in neither the articles nor account_facts.
- `onb-01-first-board` (onboarding agent, v2): judge: 2/5: The reply does not answer the question: it says "I've shown you how to create your first board" but gives no steps, so the customer cannot act on it, which fails point 2 (answers the question).
- `onb-02-invite-whole-team` (onboarding agent, v2): judge: 3/5: Point 1 (grounded) fails: the claim that team members who already have an account won't use up a seat appears in neither the articles nor account_facts, and the bulk-invite article actually lists 'already a user' as an address Relay rejects.
- `onb-03-calendar` (onboarding agent, v2): judge: 3/5: Grounding fails: the reply states as fact that connecting the calendar completes the 'connect an integration' setup step, but neither the articles nor account_facts say a calendar connection counts toward that step.
- `onb-05-invites-not-arriving` (onboarding agent, v2): judge: 3/5: Point 1 (grounded) is weakened because the reply says 'once these come through, you'll have 4 people', but account_facts already shows 4 seats assigned, so it misstates the account and implies that completing the invite-five-users step is more certain than the facts support.
- `onb-11-is-sso-in-my-edition` (onboarding agent, v2): judge: 3/5: The reply offers to pass the request to a colleague so the customer won't have to explain again, a handoff capability and commitment that neither the articles nor account_facts support, which fails the grounding and no-promises points.

## Mailbox classifier: hand-written cases

| Case | Result | Classified as -> action |
|---|---|---|
| `mbx-01-out-of-office-german` | passed | out_of_office (0.97) -> ignore |
| `mbx-02-unsubscribe-polite` | passed | unsubscribe (0.95) -> opt_out |
| `mbx-03-complaint-outranks-unsubscribe` | passed | complaint (0.93) -> cta |
| `mbx-04-left-company` | passed | left_company (0.95) -> mark_contact_gone |
| `mbx-05-buying-outranks-question` | passed | buying_intent (0.85) -> cta |
| `mbx-06-meeting` | passed | meeting_request (0.94) -> cta |
| `mbx-07-product-question` | passed | product_question (0.93) -> agent_or_cta |
| `mbx-08-too-short-to-tell` | passed | other (0.20) -> review |
| `mbx-09-sarcastic-complaint` | passed | complaint (0.95) -> cta |
| `mbx-10-on-leave-not-gone` | passed | out_of_office (0.95) -> ignore |

## Mailbox classifier: accuracy against the simulator's labels

160 replies, evenly sampled. Accuracy **96%** (plain replies 100%, deliberately hard ones 84%).

| Intent | Replies | Precision | Recall |
|---|---|---|---|
| buying_intent | 21 | 87% | 95% |
| complaint | 20 | 85% | 85% |
| left_company | 20 | 100% | 100% |
| meeting_request | 27 | 100% | 100% |
| out_of_office | 20 | 100% | 100% |
| product_question | 35 | 97% | 100% |
| unsubscribe | 17 | 100% | 82% |

Confusion matrix (rows: what it was; columns: what the classifier said).

| | buying_intent | complaint | left_company | meeting_request | out_of_office | product_question | unsubscribe |
|---|---|---|---|---|---|---|---|
| **buying_intent** | 20 | 0 | 0 | 0 | 0 | 1 | 0 |
| **complaint** | 3 | 17 | 0 | 0 | 0 | 0 | 0 |
| **left_company** | 0 | 0 | 20 | 0 | 0 | 0 | 0 |
| **meeting_request** | 0 | 0 | 0 | 27 | 0 | 0 | 0 |
| **out_of_office** | 0 | 0 | 0 | 0 | 20 | 0 | 0 |
| **product_question** | 0 | 0 | 0 | 0 | 0 | 35 | 0 |
| **unsubscribe** | 0 | 3 | 0 | 0 | 0 | 0 | 14 |

Costly misses (an unsubscribe or a complaint read as something else): **6**.
- `M000079`: was complaint, read as buying_intent
- `M000109`: was unsubscribe, read as complaint
- `M000181`: was unsubscribe, read as complaint
- `M000208`: was unsubscribe, read as complaint
- `M000343`: was complaint, read as buying_intent
- `M000436`: was complaint, read as buying_intent

## Account briefs

| Case | Result | Brief used |
|---|---|---|
| `brf-01-seats-nearly-full` | passed | AI-written |
| `brf-02-at-the-rule-limit` | passed | template (the fallback) |
| `brf-03-growing-but-unhappy` | passed | template (the fallback) |
| `brf-04-renewal-is-close` | passed | template (the fallback) |

## How to read this

- A case passes only when every check written in code passes. The judge is asked only
  about answers that already passed those checks, and scores wording and grounding.
- A new prompt version becomes the default only when it does not lose a case the old
  one passed in the hard-rule categories (pricing, contract, person, frustration).
- Handoffs that people close as "the agent should have handled this" become new cases
  under `evals/cases/from_feedback/`.
