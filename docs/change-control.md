# Change control: how an agreed decision gets reopened

Synthetic data, fictional company. Plays, thresholds, prompts and schemas are agreed
between teams. This is how one of them changes without surprising the others, and without
every small edit waiting a week.

## The five steps

**1. A written request.** A pull request using `.github/pull_request_template.md`. It says
what changes, why, what it affects (which plays, tables, queues, teams) and the evidence
(an experiment report, an eval report, a data-quality finding, a customer complaint).

**2. Triage,** by the Digital Success Portfolio Lead, within one working day.

| Fast track: merged after one review | Full review: goes to the weekly meeting |
|---|---|
| A copy edit to an email or in-app template | A new data source or a new field in the contract |
| A threshold moved inside its agreed range | A schema change to a production table |
| A new help article or search keyword | A new play, or a play moved to a new segment |
| A new evaluation case | A new agent capability or tool |
| A queue capacity number | A change to an escalation rule or to consent handling |
| | A change to a play's success metric or holdout |

Anything that changes who is contacted, what an agent may do, or how success is measured
is a full review. If in doubt, it is a full review.

**3. Weekly architecture review.** Thirty minutes, the owners in `docs/ownership-map.md`.
One question per request: does the evidence justify the change, and who is affected.

**4. The decision is logged.** Accepted or not, as an ADR in `docs/decisions/` (context,
options, decision, consequences, revisit if). A changed play gets a new `version`, which
reshuffles its holdout on purpose so old and new results are never mixed.

**5. Safe release.**

- Tests pass: `pytest`, the dbt data tests, the contract check, and for agent changes the
  evaluation suite with no loss in the hard-rule categories.
- A new play, or a play in a new segment, starts on a 10% slice.
- The owners of affected queues are told before it ships.
- Rollback is stated in the request. For configuration it is reverting the commit.

## What is deliberately not here

No approval board for copy edits. No change freeze. The aim is that a threshold can move
the same day and a schema cannot move by accident.