# Demo script: five minutes

Synthetic data, fictional company. Start the app first: `uv run python run.py app`.
Have the Human console signed in as Sales in a second browser tab (password `demo`
locally).

Times are targets. If something breaks, say what should have happened and move on.

**Whose screen is it?** Say it as each page opens. It tells the listener that this one
app stands for several tools, each used by different people.

| Page | At a company, this is the screen of |
|---|---|
| Overview; results on Plays and experiments | Customer-success leadership (a BI dashboard) |
| Data quality | Data Engineering |
| Accounts | A success manager before a customer call. Data Science owns the scores |
| Play catalog on Plays and experiments | CS Operations, who run the journeys |
| Live demo | The customer. Nobody else sees this conversation live |
| Human console | Success managers and Sales. The only page with a sign-in |
| Agents | The AI agent engineers |
| Pilot, Operating model | This role |

The workflow is drawn at the top of the Overview page, with the team accountable for each
step. Start there: it frames everything that follows. Under it, "The role, line by line"
lists the ten lines of the role and the page that shows each one.

**1. Frame it (30 seconds). Overview page.**

> "I built a small version of this role last week, on fictional data, to make sure I
> could do every piece of the job description, not just talk about it. In the real job
> these pieces live across Databricks, Gainsight, Salesforce and Tableau; here they're in
> one system so you can see how they connect."

Point at "The measures the pilot is run on" (usage, agent invocation, handoff rate,
retained revenue with the holdout beside it), then at the row "From signal to outcome":
signals, plays, touches, agent conversations, handoffs, closed.

**2. Data (45 seconds). Data quality page.**

> "Raw telemetry lands and is validated. Bad events go to a dead-letter table with a
> reason; nothing is silently dropped. dbt builds the production tables with a hundred
> tests, and the main table has a written contract that code checks on every run."

Show the rejected-by-reason chart and the contract checks.

**3. Signals and models (45 seconds). Accounts page.**

Filter to health band red, open the first account.

> "One account. The health score and why: five components. The signals firing, each with
> its evidence. Churn and expansion scores with reasons in plain words. The churn flag is
> not a fixed threshold: the team can work forty accounts, so the top forty are flagged."

Open the audit log expander: "And every decision about this account, including why it was
not put in a play."

**4. Play, agent, human fallback (60 seconds). Live demo page.**

Stay on the first account in the list. Point at the blue box: the signal firing today,
the play it triggers, and whether this account is in the play or held out.

Type: `How do I invite my whole team at once?` (or press **Run the story**, which sends
this message and the next one in one click, with no typing to get wrong).

> "A stalled admin. The agent checks their setup, searches the help centre, answers from
> the article."

Type: `Thanks. How much would 10 more seats cost?`

> "Pricing. A hard rule in code hands off to Sales before the model is even asked. It
> cannot be talked out of it."

Switch to the Human console tab, open the new task.

> "This is what the seller sees: why it is on their desk, the customer's own words, what
> was already tried, the account at a glance, a recommended next step. I resolve it, and
> the outcome goes back to the journey."

Resolve as `expansion_opportunity`.

**5. Measurement (45 seconds). Plays and experiments page.**

> "Every play against its holdout, on a metric named before launch. The lift, its
> interval, and a verdict from a written rule: working, too early, or no effect, with the
> smallest effect this sample could have seen. It is a simulation, so the lift is an
> assumption coming back out. The measurement is the real part."

Scroll to "One play in detail" (it opens on Onboarding rescue): the journey funnel, the
result by entry week, and revenue per group with the guardrail "still a customer".

**6. Agent quality (30 seconds). Agents page, Evaluation tab.**

> "Forty-four fixed cases, run against the real model. Code checks first: did it hand
> off, for the right reason, to the right queue. A judge model only scores the wording of
> answers that already passed. Three prompt versions ran on the same cases: the one I
> expected to win scored 25 of 30, the baseline 29, and the third, written from the
> failures, 30. The evals picked the prompt, not me."

The report states which model produced the answers. If it ever says stand-in, say so:
"this run proves the rules and the routing, not the answers."

**7. Pilot (30 seconds). Pilot page.**

> "This is how I'd run the uncovered-accounts pilot. The readiness checklist is not
> ticked by hand: each line is answered from live data when the page opens. Then a ten
> percent slice, a full test with a holdout, weekly review notes, and a scale, fix or
> stop call per play. Scaling to the next segment is one line of configuration, and the
> page already shows what that line would do: who would enter, and which queue could not
> take the first day."

Scroll to "Handoff quality" if asked about people: time to pickup, SLA breaches,
re-contact, docs gap.

**8. Operating model (15 seconds). Operating model page.**

Open the dependency map (drawn as a diagram), the ownership map, then one play spec.

> "That's how I'd keep cross-functional delivery moving, and how I'd hand work to the
> agent engineers."

**Close.**

> "Everything here maps to a line in your JD. Happy to go deeper on any piece."

## If they ask to go deeper

| Question | Where to go | The short answer |
|---|---|---|
| How do you know the model is any good? | `docs/model-cards/` | Time-based split, compared with a benchmark, precision at the team's capacity, reasons in words |
| Why not let the model decide when to escalate? | ADR 0003 | A prompt asks, code guarantees. Each rule has a test that needs no model |
| What does the agent cost? | ADR 0015 | Cached, budgeted, offline by default. One module calls the API |
| Is the lift real? | ADR 0005, 0016 | No, and the report says so. The measurement system is what is being shown |
| What would you ask Data Engineering for first? | `docs/data-requirements.md` | Coverage tier, one consent field, account id on every event |
| What does this column mean? | `docs/data-dictionary.md` (Operating model page) | 533 columns, each with a definition; a test fails when one is missing |
| Did you look at the data before building? | `analytics/01_eda.ipynb` | Six questions with charts; each signal was kept only because it points the right way |
| How does the agent get better? | Agents page, Review queue tab | An unnecessary handoff or a thumbs down becomes a draft case the next prompt must pass |
| What happens when a queue overflows? | Human console, ADR 0004 | Flags follow capacity; an alert fires at two days of backlog |
| How would this run in production? | `docs/production-architecture.md` | Same code, a `prod` profile; a table of what is real and what is simulated |

## Before the interview

- [ ] `uv run python run.py test` passes.
- [ ] Decide the mode. With the key in `.env`, add the line `DSO_OFFLINE_MODE=false` so the
      Live demo answers anything you type (cached answers are instant, new ones cost
      cents). With no network, add `DSO_LLM_STAND_IN=true` instead and say so.
- [ ] The app opens with Wi-Fi off (replay or stand-in mode).
- [ ] **Run the story** works on the first account of the Live demo page. Then remove the
      test task: it is a real row (see the note on pictures in `CLAUDE.md`).
- [ ] Do not press "Advance one day" before the conversation. A new day changes the
      accounts, and the stored answers no longer match (the agent then says it is
      unavailable and hands off). With `--live` this does not matter.
- [ ] A second tab is signed in to the Human console.
