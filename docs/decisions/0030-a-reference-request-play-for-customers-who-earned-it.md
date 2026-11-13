# 0030: A reference request play, only for customers who have earned it

Status: accepted (13 November 2026, after the phases; the owner's request of that day).
Synthetic data, fictional company.

## Context

Every play so far protects revenue or grows it: setup, usage, detractors, missing
admins, seats, editions, a second product. None turns a happy customer into an advocate,
although references and reviews are among the most valuable things a customer success
team obtains. Customers with no assigned success manager are rarely asked, because
nobody knows which of them are happy.

Asking at the wrong moment does harm: a customer with an open problem, a falling health
score or a renewal under negotiation should not receive a request for a favour.

## Options

1. **No advocacy play.** The gap stays.
2. **Ask every customer who gives a high survey score.** Simple. It ignores everything
   else the data says about the customer.
3. **A signal that requires several conditions at once, and a person's approval before
   the request is sent.**
4. **A score built from several parts**, as some teams do. It needs weights that nobody
   can validate on simulated data.

## Decision

Option 3.

- **The signal `advocate_ready`** (`dbt/models/marts/signals.sql`) fires when all of the
  following hold: the latest survey score is 9 or 10 and is at most 90 days old; the
  health band is green; the customer is at least 90 days old; no high-priority ticket is
  open; and the churn model does not flag the customer.
- **The play `advocacy_ask`** ("Reference request", `config/plays.yaml`) sends one email,
  `engine/templates/reference_request.md`, which waits for the approval of the Scaled CS
  team (ADR 0029). Nobody is chased after it. Usual exclusions apply, including a renewal
  in negotiation and another play in progress.
- **Rollout:** a new play, so it starts on the 10% slice.
- **Holdout: 10%.** The success measure cannot be compared fairly with the holdout,
  because a customer who is never asked cannot accept. The holdout is there to check the
  guardrail: asking must not hurt retention (`retained_30d`).
- **Success measure `advocate_responded`:** the contact clicked the "Yes" link of the
  request within 30 days (`metrics_play_outcomes`, from the email engagement table).

## Consequences

- The catalog now has eight plays, and the Overview's list of signals has eleven.
- The simulator has no special behaviour for this email. Clicks follow the same rules as
  any other email, so the measured acceptance rate says nothing about real customers.
- The holdout comparison of the success measure is not meaningful, and the experiment
  report reads it like any other. The guardrail is the comparison that matters here.

## Revisit if

- References become a tracked object (in the CRM): measure a reference given, not a
  click.
- The team wants reviews as well as references: a second step, or a second play, with
  its own approval.
