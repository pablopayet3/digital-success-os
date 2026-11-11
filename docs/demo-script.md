# Demo script: five minutes

Synthetic data, fictional company. Start the app first: `uv run python run.py app`.
Have the Human console signed in as Sales in a second browser tab (password `demo`
locally).

Times are targets. If something breaks, say what should have happened and move on.

**1. Frame it (30 seconds). Overview page.**

> "I built a small version of this role last week, on fictional data, to make sure I
> could do every piece of the job description, not just talk about it. In the real job
> these pieces live across Databricks, Gainsight, Salesforce and Tableau; here they're in
> one system so you can see how they connect."

Point at the row "From signal to outcome": signals, plays, touches, agent conversations,
handoffs, closed.

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

Pick an account. Type: `How do I invite my whole team at once?`

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

**6. Agent quality (30 seconds). Agents page, Evaluation tab.**

> "Forty-four fixed cases. Code checks first: did it hand off, for the right reason, to
> the right queue. A judge model only scores the wording of answers that already passed.
> Each prompt version runs on the same cases before it ships."

If the report says stand-in, say so: "This run used a rule-based stand-in, so it proves
the rules and the routing, not the answers."

**7. Pilot (30 seconds). Pilot page.**

> "This is how I'd run the uncovered-accounts pilot: a readiness checklist, a ten percent
> slice, a full test with a holdout, a weekly review, and a scale, fix or stop call per
> play. Scaling to the next segment is one line of configuration."

**8. Operating model (15 seconds). Operating model page.**

Open the ownership map, then one play spec.

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
| What happens when a queue overflows? | Human console, ADR 0004 | Flags follow capacity; an alert fires at two days of backlog |
| How would this run in production? | `docs/production-architecture.md` | Same code, a `prod` profile; a table of what is real and what is simulated |

## Before the interview

- [ ] `uv run python run.py test` passes.
- [ ] The app opens with Wi-Fi off.
- [ ] The Live demo conversation above has been run once on this machine.
- [ ] A second tab is signed in to the Human console.