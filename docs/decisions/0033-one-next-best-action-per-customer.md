# 0033: One next best action per customer, across every play

Status: accepted (19 November 2026, for the case-study interview). Synthetic data,
fictional company.

## Context

The engine decides play by play: who enters, who is held out, who is kept out. A person
looking at one customer needs the opposite view: across every play, task and signal, what
is the one thing to do now, and who does it? The case study's scenario asks for exactly
this ("recommend next best actions").

## Options

1. **A score per possible action**, ranked by a model of expected value. The usual pitch.
   It needs outcome data per action that a pilot does not have yet, and its ranking cannot
   be explained in one sentence to the person who acts on it.
2. **Show every open item and let the person choose.** Honest, and it leaves the judgment
   to whoever reads it.
3. **A fixed order of precedence**, from what is already in motion to what is not, with
   everything else listed after the recommendation.

## Decision

Option 3, in `engine/next_action.py`. It reads the operational store and today's signals,
and writes nothing.

1. A task waiting for a person: that person acts, the most urgent first.
2. A draft waiting for approval: a success manager decides.
3. A play under way, or a holdout: let the play run (its next step and date), or leave
   the customer alone until the comparison ends.
4. A firing signal: the play it starts at the next run; or, when the engine kept the
   customer out, why, and what would unblock it when a person can (find an admin, close
   the open task first).
5. Nothing firing, but health red: a success manager reviews the customer, because no
   rule will act.
6. Otherwise: no action, with the reason.

The Accounts page shows the first that applies, with who and why, then every other one.

## Consequences

- The customer hears from one voice at a time: while a person works on it, the panel says
  the plays wait, which is what the engine's exclusions already do.
- Every recommendation is explained by the data behind it. Nothing is ranked by a number
  nobody can check.
- It is a view, not a decision maker: the engine still decides entries, and people still
  decide outcomes.

## Revisit if

The pilot has enough outcomes per play and segment to estimate which action works best for
which customer. Then the order within step 4 can follow measured lift instead of the
catalog's priority.
