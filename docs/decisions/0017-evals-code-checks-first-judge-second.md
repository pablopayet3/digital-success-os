# 0017: Evaluating the agents: checks in code first, an LLM judge second

Status: accepted (Phase 6). Synthetic data, fictional company.

## Context

A prompt change can fix one behaviour and break another. Without a fixed set of cases,
nobody knows which. The agents here have two kinds of behaviour: things that must always
happen (a pricing question goes to Sales) and things that are a matter of quality (is the
answer clear and grounded in the article).

## Options

1. Read some transcripts after each change. Does not scale and is not repeatable.
2. An LLM judge for everything. Flexible, but it costs a call per case, it can be wrong,
   and it can change its mind between runs.
3. **Checks in code for everything code can decide, a judge only for the rest.**

## Decision

Option 3 (`evals/run.py`, cases in `evals/cases/`).

- **About 45 cases in three suites**: 30 conversations for the onboarding agent, 10
  mailbox replies that are easy to misread, 4 account briefs. Each case names its play,
  so every play spec lists its own cases.
- **Code checks decide first**: did it hand off, with the right reason code, to the right
  queue; was the agent model never called for a pricing message; did it search the docs
  and find the right article; did any reply contain a price. These are free and exact.
- **The judge scores only answers that already passed**, on four points: grounded in the
  retrieved article, answers the question, short and clear, no promises. It uses the
  small model and structured output, and it is cached like every other call.
- **Prompt versions are compared on the same cases.** Every run executes each agent case
  with `v1` and `v2` and reports pass rates by category and the cases that flipped. A new
  version ships only if it loses nothing in the hard-rule categories.
- **The mailbox classifier is also scored against the simulator's labels**: accuracy, a
  confusion matrix, and a count of the two mistakes that cost most (a missed unsubscribe,
  a missed complaint). Evaluation code is the only code allowed to read the ground truth.
- **Production feeds the suite.** A handoff closed as "the agent should have handled
  this" becomes a draft case in `evals/cases/from_feedback/`.

## Consequences

- The report states which model produced the answers. With the rule-based stand-in, the
  suite tests the code around the model; cases that need language understanding are
  skipped and the two prompt versions cannot differ. The real comparison needs one live
  run.
- A judge can be lenient or strict in ways that drift. It is never the only check on a
  safety behaviour, and its prompt is versioned with the others.
- Cases are written by the team that built the agent. They cover what we thought of. The
  feedback loop from real handoffs is what covers the rest.

## What the first live run taught

The suite was built against a rule-based stand-in. The first run with the real model
scored v1 at 21 of 30 and v2 at 19 of 30. Reading the failures, most were mine:

| Finding | Whose fault | Fix |
|---|---|---|
| The judge marked correct account facts ("4 of your 15 seats are assigned") as invented | The harness: the judge was shown the help articles but not what the agent's tools returned | The judge now sees everything the agent saw |
| A clarifying question failed the "asks first" check | The harness: the check wanted the reply to end with a question mark; the model asked and then gave an example | The check looks for a question anywhere in the reply |
| A correct edition comparison failed the "never states a price" check | The harness: the pattern matched "credits per seat per month", an allowance quoted from the help centre | Pattern removed; currency patterns kept |
| The customer got "I've shown you how..." with no steps | The agent loop: when the model wrote its answer and logged the outcome in one step, the loop kept only the closing remark | The reply is everything written in the turn; the turn ends once the outcome is logged |
| With prompt v2, the model sometimes logged the outcome and never wrote the answer | The prompt | Prompt v3 |

One fix of mine was wrong. I first made the tool refuse to log an outcome before an
answer existed. The model's usual order is to log first and answer second, so the
refusal confused it into writing nothing, and the score dropped. The raw responses
showed it within one run, and the guard was removed. Read the transcripts before
changing the code.

After the harness fixes: v1 29 of 30, v2 25 of 30. The "improved" prompt was the worse
one. v3, written from those failures, passes 30 of 30 and is now the default. That
score is on cases v3 was tuned against, so it is a ceiling until new cases arrive.

What this is worth: a stand-in can test rules and routing, but only a real model shows
how a real model behaves, and an evaluation harness needs evaluating too.

## Revisit if

The suite grows past a few hundred cases (sample it per run), or judge and human
reviewers disagree on more than about one case in ten (recalibrate the rubric with
graded examples).