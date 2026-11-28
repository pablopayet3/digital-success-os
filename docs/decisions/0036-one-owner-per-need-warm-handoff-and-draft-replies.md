# 0036: One owner per need, a warm handoff, and a draft reply for the person

Status: accepted (28 November 2026, for the case-study interview). Synthetic data,
fictional company. Extends ADR 0003 (hard-coded escalation) and ADR 0032 (live CRM link).

## Context

A customer message can need more than one team. "How much would 10 more seats cost? And
could someone help us set up single sign-on?" asks for a price, which only Sales gives,
and for a person to help with setup, which is the Customer Success team's job. The rules
stopped at the first match, so one of the two needs had no owner.

The customer was also told nothing when a person took over: the conversation simply
ended. And the person who picked up the task started from a blank reply.

At a real company, Sales works in its CRM (a task for the account owner) and Customer
Success works in its CS platform (a CTA). The Live demo said every task waited in the
Human console, which plays the CS platform, so a Sales task appeared to be in both.

## Options

1. **Keep one handoff per message**, to the most important team. Simple, but the second
   need is dropped.
2. **One task in both systems** for every handoff. Two people may answer, or each may wait
   for the other.
3. **One task per team the message needs**, each in its owner's system, each with one
   owner.

## Decision

Option 3.

- `check_message_all` returns every team a message needs, the most important first, at
  most one per team. `converse` hands off to the first and keeps the others in
  `more_escalations`; the caller creates one task for each.
- A **warm handoff**: when a rule or a failure hands off, the agent's last message tells
  the customer who takes over, about what, and within how many days (from the team's
  reply time in `config/routing.yaml`), and that they will not need to repeat anything.
  It is written by a rule, so it is the same every time and costs nothing. When the model
  itself hands off, its own reply already says so.
- A **draft reply** in every agent handoff packet (`draft_reply`), from a template, for the
  person to check, edit and send. It never quotes a price or promises what only the person
  can decide. The Human console shows it in an editable box with "Send the reply and
  close".
- On the Live demo, the Sales task goes to Salesforce (or waits in the console's Sales
  queue when the public demo does not send it), and the Customer Success task is a CTA in
  the Human console, which plays Gainsight. The CS task is linked to the customer's place
  in the play, at the play's person step, so the outcome a person records moves the play
  on. After closing, the console says in plain words what the play did, and shows the
  customer's path through the play.

## Consequences

- The scripted story's second message asks for both things, so one click shows a task in
  each system.
- Every handed-off conversation now ends with an agent message marked `kind: handoff`.
  Counts of agent answers leave it out.
- The live CRM send records the CRM task id in the packet (`crm_task_id`), because the
  hosted store's task numbers start again on every deploy.

## Revisit if

A team wants a different reply time in the message than its SLA, or the drafts should be
written by a model (then the evals must cover them first).
