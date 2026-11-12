# Operating review: Digital Success pilot

Synthetic data, fictional company. Written by `uv run python run.py review` from the warehouse, the operational store and the two reports. Nothing here is typed by hand.

**Period:** 2026-09-27 to 2026-10-27 (simulated calendar). **Segment:** uncovered accounts. **In scope:** 705 accounts, $1.69M ARR.

> This is a simulation. Customer reactions follow the assumptions in
> `config/sim_effects.yaml`, so the lifts below are those assumptions measured back.
> The review shows what a real one would contain and where each number comes from.

## 1. The short version

- **Working against a holdout:** Onboarding rescue.
- **Not proven, keep testing:** Usage recovery, Seat expansion.
- **Too early to read:** Detractor save, Edition upgrade, Cross-product (Docs).
- **Agent:** 50 conversations, 26% handed to a person.
- **People:** 372 tasks, 23% past their SLA, 6 open now.
- **Data:** 100 of 100 tests and 14 of 14 contract checks pass.

## 2. Leading indicators in the segment

| Indicator | 30 days ago | Now | Change |
|---|---|---|---|
| Monthly active users (sum) | 4,166 | 4,774 | +608 |
| Setup steps completed (average) | 66% | 69% | +2.5 points |
| Seat utilisation (average) | 61% | 64% | +2.8 points |
| Health score (average) | 67.3 | 68.7 | +1.4 |
| Accounts with red health | 32 | 23 | -9.0 |
| Assist invocations in 30 days | 3,741 | 4,682 | +941 |

These describe the whole segment, treated or not. They say where the segment is going. Only section 3 says what the plays changed.

## 3. What the plays moved, against their holdouts

| Play | Stage | Success metric | Treatment | Holdout | Lift (95% interval) | Reading |
|---|---|---|---|---|---|---|
| Find the admin | full | valid_admin_restored | 69% of 65 | none | n/a | Not an experiment (no holdout) |
| Detractor save | full | retained_30d | 100% of 52 | 100% of 8 | +0% (+0% to +0%) | Too early |
| Onboarding rescue | full | setup_completed | 41% of 46 | 2% of 55 | +39% (+25% to +54%) | Working |
| Usage recovery | full | usage_recovered | 32% of 31 | 13% of 23 | +19% (-2% to +41%) | No effect detected |
| Edition upgrade | slice | expanded_30d | 17% of 6 | 50% of 2 | -33% (-109% to +42%) | Too early |
| Seat expansion | full | expanded_30d | 19% of 83 | 21% of 57 | -2% (-15% to +12%) | No effect detected |
| Cross-product (Docs) | slice | docs_adopted | 0% of 4 | 0% of 3 | +0% (+0% to +0%) | Too early |

**Expansion sourced by Edition upgrade:** $1,096 closed in treatment ($183 per account) against $1,806 in the holdout ($903 per account).

**Expansion sourced by Seat expansion:** $24,351 closed in treatment ($293 per account) against $14,790 in the holdout ($259 per account).

Full detail, cohorts and split checks: `experiments/reports/experiment-report.md`.

## 4. What ran, by rung of the ladder

311 accounts entered a play and 153 were held out for comparison. 36 contacts opted out and were removed the same day.

| Rung | Channel | Touches delivered |
|---|---|---|
| agentic | agent | 44 |
| digital | email | 89 |
| digital | in_app | 23 |
| human | task for a person | 372 |

## 5. The agents

- **Onboarding agent:** 50 conversations (agent invocations), 37 answered, 13 handed off (26%). Model cost: $1.26.
- **Replies written by:** claude-opus-5-5, no agent model: a hard rule stopped it first.
- **Why it handed off:** pricing_contract_legal (8), customer_asked_for_person (3), not_in_docs (1), frustration (1).
- **Docs gap:** 1 handoffs because no help article covered the question. Each one names an article to write.
- **Mailbox triage:** 613 replies read. missed_product_question (108), ignored (89), contact_marked_gone (68), missed_meeting_request (60), account_not_active (43), missed_buying_intent (37), missed_complaint (37), opted_out (36), cta_complaint (33), cta_meeting_request (26), agent_answered (24), contact_gone_no_admin_left (23), cta_buying_intent (20), human_review (7), agent_handed_off (2).
- **Voice of the customer:** 1083 comments and tickets read; 499 negative. What they are unhappy about: performance (157), setup (112), usability (85), pricing (84).
- **Evaluation** (answers by: offline (replaying cached model responses)): onboarding agent (v1) 29 of 30, onboarding agent (v2) 25 of 30, onboarding agent (v3) 30 of 30, mailbox cases 10 of 10, briefs 4 of 4.

## 6. What people had to pick up

| Queue | Tasks | Open now | Past SLA | Closed with a good outcome | Unnecessary |
|---|---|---|---|---|---|
| pooled_csm | 155 | 4 | 26 | 70% | 10 |
| sales | 120 | 2 | 27 | 47% | 0 |
| admin_research | 90 | 0 | 34 | 67% | 0 |
| human_review | 7 | 0 | 0 | 71% | 2 |

Escalation conversion (tasks closed as resolved, saved or an expansion opportunity): 62%. Unnecessary handoffs ("the agent should have handled this"): 3%; each becomes an evaluation case.
Capacity alerts: 16 in the period, on admin_research, pooled_csm, sales. Latest (2026-10-05): CS Operations (contact research): 23 open CTAs, capacity 8 a day. Working by priority, then SLA.

## 7. Can the data be trusted

- 100 of 100 data tests pass. 14 of 14 checks on the contract of the production table pass.
- 617,555 product events were kept. 8,385 (1.3%) were rejected at ingest and kept with a reason. The largest reason is a missing account id, which is an ask to Product Engineering (`docs/data-requirements.md`).

## 8. Decisions requested

| Play | Owner | Decision requested |
|---|---|---|
| Find the admin | CS Operations lead | Keep running; track the rate. |
| Detractor save | Scaled CS team lead | Keep testing. |
| Onboarding rescue | Digital Success Portfolio Lead | Scale: move to the next rollout stage or the next segment, and keep a holdout. |
| Usage recovery | Digital Success Portfolio Lead | Keep testing until the sample can detect the lift that would justify the play. |
| Edition upgrade | Digital Success Portfolio Lead, with Sales | Keep the slice running. |
| Seat expansion | Sales lead, with Digital Success | Keep testing until the sample can detect the lift that would justify the play. |
| Cross-product (Docs) | Digital Success Portfolio Lead | Keep the slice running. |

Each decision is a reviewed change to `config/plays.yaml` or `config/rollout.yaml` (`docs/change-control.md`). A play that scales keeps a 10% holdout.
