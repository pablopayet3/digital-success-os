# 0016: Experiment design for the pilot: large holdouts, leading indicators, a decision rule

Status: accepted (Phase 6). Synthetic data, fictional company.

## Context

Every play claims to change customer behaviour. Without a comparison group, any change
could be seasonality, a product release, or accounts that would have recovered anyway.
The pilot runs on one segment (`uncovered`) for 30 days, with a few dozen eligible
accounts per play. That is a small sample and a short window.

## Options

1. Before and after: compare accounts with themselves. Cheap, and wrong whenever anything
   else changed at the same time.
2. A small holdout (5 to 10%), as a mature programme would run. With 80 eligible accounts
   that is 4 to 8 holdout accounts: no comparison is possible.
3. **A 50% holdout during the pilot**, judged on a leading indicator that can move in 30
   days, with retention watched as a guardrail.

## Decision

Option 3.

- **Holdout by hash**, 50% for plays under test (20% for the detractor play, because
  withholding help from an unhappy customer has a cost; none for data hygiene). A holdout
  account is a real enrolment: it is reserved for the window, so no other exclusive play
  contaminates the comparison (ADR 0014).
- **One success metric per play, declared in `config/plays.yaml` before launch.** Setup
  finished, usage recovered, expansion closed, first doc published. Thirty days cannot
  show churn, so churn is not a success metric for any play.
- **Outcomes are computed in the warehouse** (`gold.metrics_play_outcomes`) from
  telemetry, the CRM and the operational store, the same way for both groups. dbt
  computes all six outcomes for every enrolment; the play config says which one counts.
- **The analysis is a two-proportion z-test** with a 95% interval on the lift
  (`experiments/analyze.py`). It is the simplest correct test for "did a larger share of
  one group reach the goal", and it can be explained on a whiteboard.
- **Three protections against fooling ourselves**: a sample-ratio check (if the split is
  far from the one designed, the result is not read); a minimum of 20 accounts per group and 7
  days observed; and the smallest lift the sample could have detected, printed next to
  every "no effect".
- **A decision rule, written down**: significant and positive, scale to the next stage or
  segment and keep a holdout; significant and negative, stop; otherwise keep testing.

## Consequences

- Half the eligible accounts get nothing during the pilot. That is the price of knowing.
  Once a play has proved itself, the holdout drops to 10% and stays there: a permanent
  small holdout is how a programme keeps proving its value.
- Several plays will end the pilot as "too early". That is a correct result, and the
  report says how large a lift the sample could have seen.
- With seven plays and a 5% bar, one false positive is not unlikely. A play is scaled on
  a result that holds across weekly cohorts, not on a single p-value.
- The window can still be open when the report is read. Both groups enter on the same
  days, so "so far" is a fair comparison; the report shows the days observed.

## What happened the first time the split check ran

On the first clean 30-day run the check fired on the seat-expansion play: 91 treatment
and 58 holdout against a 50/50 design (p = 0.008). The first version of the rule said
"below 0.01, do not read the result".

The investigation took one query. Of the 153 accounts the engine ever considered for the
play, the hash put 93 in treatment and 60 in holdout, and the engine enrolled exactly
that, minus two accounts per arm excluded for the same reasons. Exclusions are applied
before assignment, so they cannot favour an arm. Nothing was filtering one group: it was
a chance imbalance of about 1 in 130.

Two changes followed. The alarm moved to **p < 0.001**, the usual convention for this
check, because it runs on every play at every look and a 1% bar raises false alarms.
Between 0.001 and 0.01 the report now prints "uneven, watch it" rather than voiding the
result. The lesson kept: when the check fires, compare the hash split of everyone
considered with the split of everyone enrolled. If they match, it is chance. If they do
not, something after assignment is removing accounts from one arm.

## Honest limit

This is a simulation. Customers react to touches according to
`config/sim_effects.yaml`, so the lift is an assumption coming back out. The design, the
tables and the decision rule are what carry over to real data.

## Revisit if

Samples allow it: move to sequential testing with a fixed stopping rule, add
variance reduction using pre-period behaviour, and measure revenue outcomes over a
90-day window.