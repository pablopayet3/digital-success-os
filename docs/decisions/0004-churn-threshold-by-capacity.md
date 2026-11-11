# 0004: Flag as many accounts as people can act on, and no more

Status: accepted (Phase 3). Synthetic data, fictional company.

## Context

The churn model gives every account a score between 0 and 1. Something has to turn that
score into "this account gets a human conversation". The usual answer is a threshold that
maximises an accuracy measure. But a flag only has value if someone acts on it, and the
people who act (the pooled CS team for churn, account owners for expansion) have a fixed
amount of time.

## Options

1. A fixed threshold chosen for accuracy (for example the score that maximises F1). Easy to
   explain to a data scientist. Says nothing about whether the queue can be worked.
2. A fixed threshold chosen once from capacity. Better, but the customer base grows: in
   this demo the same score flagged 40 accounts on the test day and 74 three months later.
3. **A cut-off redrawn every day at the team's capacity.**

## Decision

Option 3. `config/models.yaml` states how many flagged accounts in the pilot segment each
team can carry at one time (40 churn-save conversations, 60 expansion briefs). Each day
the cut-off is the score of the account at that rank in the pilot segment; every account
at or above it is flagged (`analytics/score.py`, `flag_by_capacity`).

The model card reports what that buys: precision and recall at the cut-off, next to the
base rate. On the test day the churn flag was right about 27% of the time against a base
rate of 9%, so a flagged account is about three times as likely to churn as a random one.

The production model is a logistic regression, with gradient boosting kept as a benchmark.
Boosting ranks better on churn (AUC 0.79 against 0.72). We accept that gap in the pilot
because every flag comes with reasons a CSM can read ("few seats active, admin rarely
logs in, low NPS"), and a flag nobody trusts is worth nothing.

## Consequences

- The queue never outgrows the team. Capacity is a number the CS lead owns and can change.
- Precision is honest about what the team will experience: of 40 conversations, about 11
  are with accounts that would otherwise churn.
- An account can leave the list without getting healthier, because others got worse. The
  score is the measure of risk; the flag only decides who gets attention first.
- If capacity doubles, the cut-off drops and precision falls. That trade is visible in the
  model card, not hidden in a threshold.

## Revisit if

The team consistently clears its queue early (raise capacity), precision at the cut-off
falls below twice the base rate (retrain or fix features), or CSMs trust the flags enough
to trade the plain-word reasons for the stronger model.
