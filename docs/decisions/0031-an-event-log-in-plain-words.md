# 0031: An event log in plain words on the Overview

Status: accepted (13 November 2026, after the phases; the owner's request of that day).
Synthetic data, fictional company.

## Context

The Overview shows counts: signals, plays, messages, tasks. A reader sees how much the
system did, not what it did. The individual decisions were only visible one customer at
a time on the Accounts page, or in tables of codes (`journey_events`, `audit_log`).

## Options

1. **Leave it.** The counts are accurate, and abstract.
2. **Show the raw journey events table.** Complete, and unreadable: step ids, event codes
   and queue keys.
3. **Turn the latest events into sentences**: the customer, what the system did, the
   signal that started it, and the play.

## Decision

Option 3: `app/events.py`, shown on the Overview under "What the system did, in plain
words".

- It reads the journeys' own record (`journey_events`) and the enrolments, both in the
  operational store, and keeps the events that are actions: entering or being held out,
  an email, a message in the product, a conversation with the agent, a handoff, a draft
  and its decision, a postponed message, a goal reached. Waits and branches are left
  out.
- Each event becomes one sentence, with the team's name instead of a queue key: "Wexyx
  Energy was sent an email: … Why: setup has stalled, in the play Onboarding rescue."
- The fifteen most recent events are shown, newest first.

## Consequences

- The loop is visible at a glance, which also serves the demonstration video.
- The words for each event live in one table (`ACTIONS`). A new kind of event shows up
  only once it is given words there.

## Revisit if

The list is wanted per team or per play: add a filter, from the same function.
