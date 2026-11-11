# 0007: 180 days of history, 1,200 accounts, and labels from observed outcomes

Status: accepted (Phase 1). Synthetic data, fictional company.

## Context

The brief asked for about 600 accounts and 120 days of events, with churn and expansion
"within 90 days" stored as hidden ground truth. Three problems showed up when planning the
models and the experiments.

1. **Labels.** A churn model needs, for each training row, the account's features on some
   date and whether it churned in the following 90 days. With 120 days of data, no date
   has both a month of history behind it and 90 observed days in front of it. The model
   would have to be trained on the hidden answer key, which is not how it works in real
   life and is hard to defend.
2. **Sample size.** Seven plays run on the uncovered segment only, each with a holdout.
   With 600 accounts several plays would have fewer than 30 accounts per group, and a
   significance test would only show noise.
3. **Missing sources.** The brief uses data it never generates: opportunities (for the
   "renewal in negotiation" exclusion and the expansion pipeline) and email engagement
   (for the engagement part of the health score).

## Options

1. Follow the brief as written and train on ground truth. Fast, but the models and the
   time-based split would not be honest.
2. Keep 120 days and shorten the outcome window to 30 or 45 days. Honest, but far from
   how churn is usually defined.
3. **Lengthen history to 180 days, raise accounts to 1,200, and record churn and expansion
   where a real company would see them: in the CRM.**

## Decision

Option 3.

- 180 days of history. A snapshot on day 60 and one on day 90 both have 90 observed days
  after them. Train on the earlier snapshot, test on the later one.
- Churn is visible as `status` and `churned_at` on the account. Expansion is visible as a
  closed-won expansion opportunity. Labels are built from these in the warehouse.
- 1,200 accounts, of which 60% sign up during the simulated period, so there are weekly
  signup cohorts and enough stalled onboardings to test a play.
- Two extra sources: `crm_opportunities.csv` and `email_engagement.csv`. Contacts carry a
  `product_user_id`, so an admin's product activity can be tied to the CRM contact.
- `data/ground_truth/` keeps the hidden traits and daily hidden state. It is used only to
  check that models and scores track the truth, never as model input.

## Consequences

- About 500,000 product events instead of 250,000. Generation takes about 25 seconds and
  the files are about 100 MB. DuckDB handles this easily.
- In history, about 10% of accounts churn and 11% expand within 90 days of a snapshot.
  That is enough positive examples for a simple model.
- On the last day of history the pilot segment has about 650 active accounts, with about
  75 stalled onboardings and between 30 and 65 accounts for each other signal. More
  qualify during the 30 pilot days. The generation report prints the exact counts on
  every run (`data/ground_truth/generation_report.md`).
- Volumes are settings in `config/world.yaml`. A `small` profile keeps tests fast.

## Revisit if

A play still has too few accounts to test after the 30-day pilot simulation. Then raise
the account count or lengthen the pilot before reading anything into the results.
