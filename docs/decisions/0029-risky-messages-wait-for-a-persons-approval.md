# 0029: Risky messages wait for a person's approval

Status: accepted (13 November 2026, after the phases; the owner's request of that day).
Synthetic data, fictional company.

## Context

Until now every automated message was sent as soon as its step was due, after the
consent, pause and frequency checks. That suits a setup guide. It does not suit a
message whose cost of being wrong is high: asking a customer to act as a reference, a
save offer, anything that commits the company or spends the customer's goodwill. In
those cases a person should see the message before the customer does.

The idea came from a public example of a customer-success setup in which every agent
writes drafts into one review board, and nothing reaches a customer without a person's
approval.

## Options

1. **Send everything automatically.** Fast, and wrong for the risky messages.
2. **Make the risky step a task for a person**, who writes and sends the message
   themselves. Safe, but the person starts from nothing, and the message is no longer
   tracked as a touch of the play.
3. **A draft and an approval.** The system writes the message, a person approves or
   rejects it, and the system sends it. The person spends a minute, not ten.
4. **Approve every message.** The team would drown, and the point of digital coverage
   would be lost.

## Decision

Option 3, opt-in per step. An email step in `config/journeys.yaml` may carry
`approval: <queue>`.

- The runner writes the rendered email into the operational store's `drafts` table,
  parks the journey (status `waiting_on_human`, the same status as a handoff) and logs
  `draft_created`. Nothing is sent and no touch is recorded.
- The Human console shows the drafts of the signed-in role's queues, with Approve and
  Reject and an optional note (`engine/approvals.py::decide`).
- **Approve:** the journey resumes at the same step. The next run checks consent, the
  pause and the frequency cap again, sends the email, records the touch and marks the
  draft `sent`.
- **Reject:** the journey ends for that customer with the reason `draft_rejected`.
- In a simulation that runs on its own, simulated staff decide drafts written on an
  earlier day: 85% approved (`APPROVAL_RATE`), the rest rejected, the same way every run.
- The catalog refuses an approval on a step that is not an email, or for a queue that
  does not exist.
- The first step to use it is the reference request (ADR 0030).

## Consequences

- A person stands between the system and the customer exactly where the risk is, and
  nowhere else.
- An approved message still passes every guardrail at the moment it is sent.
- The hosted demo's store is shared: an approval there resumes the journey, but the email
  is sent only when a day is simulated, which the hosted demo does not do. The console
  says that the email goes out at the next daily run.
- Approval time adds to the play's time to first touch. It is visible in the journey's
  events (`draft_created` to `email_sent`).

## Revisit if

- A play needs a person to edit a draft, not just approve it: add an edited body column
  and send that version.
- Drafts pile up: add them to the queue capacity check, as tasks are.
