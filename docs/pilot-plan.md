# Pilot plan: uncovered accounts

Synthetic data, fictional company. Owner: Digital Success Portfolio Lead.

## Segment

**Uncovered accounts:** customers with no named success manager (`coverage_tier =
uncovered`, set in `config/rollout.yaml`). They are the largest group, the least watched,
and the safest place to learn: no existing relationship is disturbed.

## Plays and the success criteria set before launch

| Play | Starts as | Holdout | Success metric (30 days from entry) | Guardrail |
|---|---|---|---|---|
| Onboarding rescue | Full test | 50% | Setup completed (75% of steps) | Retention; opt-outs |
| Usage recovery | Full test | 50% | Usage back to 90% of the earlier level | Retention |
| Seat expansion | Full test | 50% | Expansion closed-won | Retention; complaints |
| Detractor save | Full test | 20% | Still a customer | SLA of 48 hours met |
| Find the admin | Full, no holdout | 0% | An admin we may email exists | Queue capacity |
| Edition upgrade | 10% slice | 50% | Expansion closed-won | Complaints; opt-outs |
| Cross-product (Docs) | 10% slice | 50% | First doc published | Opt-outs |

A play's metric, holdout and audience are fixed at launch. Changing one is a new play
version through change control, which reshuffles the holdout so results are never mixed.

## Readiness checklist (all must be true before a play goes to full test)

The lines that data can answer are answered from live data on the app's Pilot page
(`engine/pilot.py`, ADR 0020), with their bars in `config/rollout.yaml`. The lines that
need a person's judgement (a spec signed off, the staff briefed) stay here.

- [ ] Data: the pipeline run passes its data tests and the contract check; sources are fresh.
- [ ] The trigger signal fires on a plausible number of accounts (not zero, not everyone).
- [ ] The play has an owner, a success metric and a holdout in `config/plays.yaml`.
- [ ] Consent and the frequency cap are enforced by the engine, and tested.
- [ ] Every human step names a queue with an owner, an SLA and enough capacity.
- [ ] For agent plays: the evaluation suite passes on the hard-rule categories.
- [ ] The play spec in `docs/play-specs/` is signed off by its owner and by agent engineering.
- [ ] The slice ran for a week with no complaint, no failed step and no queue alert.
- [ ] The people working the queues have seen a handoff packet and know the outcomes to record.

## Staged rollout

1. **Slice (week 1).** 10% of eligible accounts. Question: does anything break? Watch
   failed steps, complaints, opt-outs, queue alerts.
2. **Full test (weeks 2 to 8).** Every eligible account in the segment, split by hash
   into treatment and holdout. Question: does it move the metric?
3. **Decision (weeks 6 to 8).** Scale, fix or stop, per play.
4. **Next segment.** Add `pooled` to `config/rollout.yaml`. Same plays, same guardrails,
   10% holdout. A test in the repository proves the second segment runs unchanged.

## Weekly review (30 minutes)

Read from the experiment report and the app, in this order:

1. Data quality: any failed test or stale source this week?
2. Guardrails: opt-outs, complaints, queue alerts, SLA breaches.
3. Each play: accounts entered, rate in treatment and holdout, the interval, the split check.
4. Handoffs: volume per queue, unnecessary handoffs, the docs-gap list.
5. Agent: evaluation pass rate; new cases from feedback.
6. Decisions and changes requested (through change control).

## The decision after six to eight weeks

| Result | Decision |
|---|---|
| Positive, unlikely to be chance (p < 0.05), consistent across weekly cohorts, guardrails clean | **Scale:** next segment, holdout down to 10% and kept |
| Positive but the interval still includes zero | **Keep testing** until the sample can detect the lift that would justify the cost |
| No effect, and the sample could have detected a worthwhile one | **Fix or stop:** change the trigger, the message or the rung, as a new version; or retire it |
| Negative, or a guardrail broken | **Stop** now and review |
| The split is not the one designed | **Do not read the result.** Find the cause first |

## What 30 days can and cannot show

Thirty days can show whether setup finishes, whether usage recovers and whether a seller
closes an expansion. It cannot show churn. That is why each play is judged on a leading
indicator and retention is a guardrail. A 90-day read on revenue follows the pilot.
