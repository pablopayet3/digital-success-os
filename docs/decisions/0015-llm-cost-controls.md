# 0015: LLM cost controls: cache, budget, offline by default, models in config

Status: accepted (Phase 5). Covers brief update item 21. Synthetic data, fictional company.

## Context

The LLM API is the only paid service in this project. Three things could go wrong: a loop
that runs up a bill, a live demo that fails because the network or the API is down, and a
key that leaks through a hosted demo.

## Decision

One module, `agents/llm.py`, is the only code that calls the API. It enforces four rules.

**1. Cache every response.** A response is stored in `cache/llm/` under a fingerprint of
the exact request (model, effort, instructions, messages, tools, output schema). The same
request again is read from disk: free, instant, identical. The cache is committed, so
anyone who clones the repo can replay the demo without a key.

**2. Offline is the default.** In offline mode a request that is not in the cache is not
sent. The caller gets `LLMUnavailable` and takes its documented fallback: an agent hands
off to a human, a brief falls back to its template, a classifier leaves the item for later.
Demos, CI and the hosted app run offline, so they never call the API and hold no key.

**3. A run stops at its limits.** `MAX_LLM_CALLS_PER_RUN` (400) and `LLM_BUDGET_USD` (5)
are checked before every paid call. At either limit `LLMBudgetReached` is raised, the call
is not made, and the run ends by printing calls made, calls served from cache, and dollars
spent. Simulated agent conversations are also capped at 50 per run.

**4. Models are config.** `config/llm.yaml` assigns a model and an effort level to each
job. The small model does classification, customer simulation, judging and briefs. Only
the agent's replies to customers get the stronger model. The file also holds the price
list used to count spend, and the prompt version in use.

| Job | Model | Why |
|---|---|---|
| Agent replies to customers | Claude Opus 5.5, low effort | The one place quality is customer-facing |
| Message and mailbox classification | Claude Haiku 5.5 | Few categories, plain names, high volume |
| Customer simulation, LLM judge, briefs | Claude Haiku 5.5 | Checked by code or by a rubric |

Changing the agent to Claude Sonnet 5.5 is a one-line config edit and halves its cost.

Other choices that keep cost down: classification is batched (eight texts per call) and
identical texts are classified once; the simulated customer in the daily run is scripted,
not generated; the system prompt is marked cacheable on the API side.

## Consequences

- Tests use a stand-in transport and need no key. They cover the cache, offline mode and
  both limits.
- A cached answer is only as current as the prompt and the data that produced it. Changing
  a prompt, a tool description or an account's numbers changes the fingerprint, so the
  next online run pays for a fresh answer. That is intended.
- Thinking cannot be switched off on the agent model; effort is the control. Low effort is
  enough for short support replies and is the cheapest setting.
- If the agent model declines a request for safety reasons, the API retries on a fallback
  model (a config flag). If the result is still a refusal, the conversation is handed off.

## The stand-in

Offline mode replays real responses, so it needs a cache that one live run has filled.
Before that run, and on any machine without a key, a rule-based stand-in
(`agents/stand_in.py`) plays the model: keyword rules that return responses in the API's
shape. It lets the whole flow run (tools, retrieval, escalation, handoffs, mailbox
routing) at no cost. Its answers are stored apart from the real cache, and the model name
in every trace and on every screen is "stand-in (keyword rules, not an LLM)".

It is switched on with `llm_stand_in: true` (the dev default until the cache is filled)
or `DSO_LLM_STAND_IN`. It tests the code around the model. It says nothing about how
well a real model answers, and evaluation reports state which one produced them.

## Not yet verified

No real API call has been made yet: there was no key on the build machine. The request
shapes follow the current API reference. The first online run may need small fixes.

## Revisit if

Spend per run is far below the budget (lower it), or the cache grows large enough to
bloat the repository (move it to object storage and keep a small demo subset in git).
