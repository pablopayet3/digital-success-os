# 0024: The public demo answers with the real model when its host has a key

Status: accepted on 12 November 2026, by the owner's decision. Synthetic data, fictional company.

## Context

ADR 0015 kept the hosted app away from the paid API: it ran the labelled stand-in, held no
key, and could not spend anything. That is safe, and it has a cost. The first thing a
visitor reads on the public demo is that the agent's answers are keyword rules, not a
model. The owner wants a visitor to talk to the real model, with a hard limit of five
dollars, and wants the screen to say so clearly when the limit is reached.

A new conversation with the real model costs about three cents. A handful of reviewers
cost a dollar or two. The risk is elsewhere: the link is public and always on, so anyone
can type to the agent.

## Options

1. Keep the stand-in on the public demo (ADR 0015 as it was).
2. Always call the model on the public demo. A wrong key or a spent balance then shows
   every visitor an agent that cannot answer.
3. Call the model when the host has a key, and count the spend in memory as every other
   run does. A free host restarts an idle app, and each restart would start the count
   again from zero: a limit in name only.
4. **Call the model only when the host has been given a key, keep the running total in
   the database, stop at five dollars, and let the labelled stand-in answer from then on
   and whenever the model cannot.**

## Decision

Option 4.

- `scripts/start-app.sh`: when `ANTHROPIC_API_KEY` is set in the host's dashboard, the app
  starts in live mode with a budget of 5 dollars. Without the key nothing changes: the
  stand-in answers and nothing is spent. Removing the key is the off switch.
- `agents/ledger.py`: every paid call is one row in the table `llm_spend` of the
  operational store. Before a paid call, the total is read from that table. At five
  dollars no further call is made. Restarting the app does not reset it. Neither does an
  admin's "Reset the demo data": the table is not one of the demo tables.
- `agents/llm.py`: with `DSO_STAND_IN_WHEN_UNAVAILABLE`, a request the model cannot answer
  (the budget is used up, no balance, a bad key, an outage) is answered by the stand-in.
  That answer costs nothing, is never saved among the real responses, and carries the
  stand-in's name, so the conversation still says truthfully who wrote each reply.
- The screen says it. The Live demo page shows what the demo may spend and what is used
  so far. When the budget is used up it shows a warning instead, and the line at the top
  of every page changes to the stand-in.
- A visitor's message is limited to 400 characters and a conversation to four turns.
- Every answer is cached, so the scripted story costs money once and is free after that.

## Consequences

- The key is typed by the owner into the host's dashboard. It is in no file and no chat.
- The limit can be passed by a few cents: two visitors can each start a call just under
  it. It cannot be passed by more.
- If the total cannot be read (the database is down), nothing more is spent.
- To allow more, the owner raises `LLM_BUDGET_USD` in the dashboard. The history stays in
  the table.
- The account's own prepaid balance is still the last line of defence. Automatic top-up
  should stay off.
- The API service keeps the stand-in. It holds no key.
- Answers stored before the change still say the stand-in wrote them.
- This changes one of the brief's cost rules (the hosted app never calls the API), on the
  owner's instruction.

## Revisit if

The demo stays public for months, or more than one person needs to raise the limit: then
the limit needs an owner, an alert before it is reached, and a monthly reset.
