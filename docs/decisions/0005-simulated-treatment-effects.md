# 0005: A day-by-day simulated world, with treatment effects as a stated assumption

Status: accepted (Phase 1). The effect sizes are set in Phase 4. Synthetic data, fictional company.

## Context

There are no real customers, so every outcome in this demo is simulated. Two things
follow. First, the lift a play shows is an assumption we put in, not a finding. Second,
the way we put it in decides whether the rest of the system is exercised honestly.

The brief proposed generating all telemetry up front and adding a treatment effect to the
outcomes afterwards.

## Options

1. **Up-front generation, effect added to outcomes at the end** (the brief). Fast and
   simple. But telemetry never reflects a play: an account "rescued" by the onboarding
   agent still looks stalled in the tables, journey branches such as "did the setup step
   close?" have nothing real to read, and the experiment is not measured from the gold
   tables.
2. **A day-by-day world that reacts to touches.** `World.step(interventions)` produces one
   day of everything. History is 180 steps with no interventions. During the pilot, each
   simulated day is: the world produces today's telemetry (reacting to yesterday's
   touches), the pipeline runs, the engine acts. Lift is then measured from the gold
   tables, exactly as it would be in production.

## Decision

Option 2. The simulator is built as a day-stepper from Phase 1. In Phase 1 the
`interventions` argument is recorded but has no effect. In Phase 4 a small, documented set
of effect sizes (kept in config, hidden from the engine and the models) makes customers
respond to touches.

How the hidden world works, in short:

- Each account has three hidden traits between 0 and 1: `engagement_propensity`, `fit` and
  `growth` (plus a few derived ones, such as `setup_drive`).
- A hidden `momentum` drifts toward a level set by `fit`. Shocks (a champion leaves) and
  runs of support problems push it down. Not finishing setup lowers it.
- Usage follows momentum, and the chance of churning rises steeply as momentum falls. So
  usage really does drop before churn, and the models have a true pattern to find.
- Seat growth follows `growth`; expansion becomes likely when nearly all seats are taken.
- Randomness for a day depends only on (seed, day number), so every run is identical.

## Consequences

- The measurement machinery is real even though the customers are not: holdout assignment,
  outcome tables, the z-test and the confidence intervals all work on pipeline output.
- We must say clearly, in the README and the app, that effect sizes are assumptions. A
  "significant lift" here proves the system can detect an effect, not that the play works.
- Simulating 30 pilot days takes a few minutes, because the pipeline runs once per day.
- If Phase 4 runs short of time, we can still fall back to option 1.

## Revisit if

Real outcome data becomes available (then the simulator is only for tests), or the
per-day pipeline run makes the demo build too slow.
