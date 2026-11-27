# 0035: No holdout for unhappy customers

Status: accepted (27 November 2026, for the case-study interview). Synthetic data,
fictional company. Changes the detractor exception in ADR 0014 and ADR 0016.

## Context

The detractor play (a survey score of 0 to 6) sends the customer straight to a person.
It held out 20% of qualifying customers, to measure whether the call made a difference.
The pilot design presented to the panel says the opposite: an unhappy customer always
reaches a person within 48 hours, in every tier, with no holdout. The working model and
the design disagreed, and the Plays page and the BI dashboard showed the difference.

## Options

1. **Keep a 20% holdout.** Measures the play, but deliberately leaves one unhappy customer
   in five without the call.
2. **No holdout.** Every unhappy customer gets the call. The play is tracked (retention at
   30 days, time to pick up the task), not tested against a comparison group.
3. **A holdout on the wording or the channel only**, never on whether a person calls.

## Decision

Option 2: `holdout_pct: 0.0` for `detractor_save`, like `find_the_admin`. Withholding help
from a customer who has just said they are unhappy costs more than the measurement is
worth. If the team later wants to improve the play, option 3 tests how a person calls,
not whether they call.

## Consequences

- The Plays page and the experiment report show the detractor play as tracked, without a
  holdout and without a verdict.
- The world simulator now sends every detractor to a person, so the synthetic outcomes
  change slightly; the demo data is rebuilt on the next deploy.
- The BI extract no longer carries a holdout rate for this play.

## Revisit if

The human CS team cannot take every detractor within 48 hours. Then the fix is capacity or
priority, not a holdout.
