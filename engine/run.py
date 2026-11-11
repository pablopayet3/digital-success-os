"""One simulated day, end to end. Then the next.

Synthetic data, fictional company.

Run with:  uv run python run.py run-day         (one day)
           uv run python run.py run-days 30     (thirty days)

A simulated day has three beats, in the order a real day would have them:

  1. The world moves.   Customers react to yesterday's touches and live a day; a new
                        file of telemetry and fresh CRM snapshots land.
  2. The pipeline runs. Ingest, dbt, scores, signals: the gold tables now describe today.
  3. The engine acts.   Staff work their queues (return signals), the rules engine
                        enrols accounts, and the journey runner delivers today's touches.

Tomorrow's first beat picks up today's touches. That is the closed loop: lift is
measured from what the pipeline saw, not added afterwards.
"""

from __future__ import annotations

import json
from pathlib import Path

# Importing the agents also plugs the onboarding agent into the journey runner.
from agents import feedback, mailbox
from agents.llm import get_llm
from analytics.train import MODEL_DIR
from common.paths import DATA_DIR
from common.store import Store, open_store
from engine import handoff, humans, journeys, rules
from engine.catalog import load_catalog
from engine.context import load_day
from ingest.pipeline import run_pipeline
from synth.generate import advance_one_day, write_ground_truth
from synth.world import World


def run_day(
    data_dir: Path = DATA_DIR,
    world: World | None = None,
    model_dir: Path = MODEL_DIR,
    verbose: bool = True,
) -> dict:
    """Simulate one day. Returns a summary of what happened."""
    truth = data_dir / "ground_truth"
    world = world or World.load(truth / "world_state.pkl")
    store, catalog = open_store(data_dir), load_catalog()

    # 1. The world moves, reacting to the touches of the engine's last run.
    interventions = pending_interventions(store, world.last_day.isoformat())
    advance_one_day(world, data_dir, interventions)

    # 2. The pipeline runs (without the slower checks; `run-days` runs them at the end).
    run_pipeline(data_dir, verbose=False, model_dir=model_dir, checks=False)

    # 3. The engine acts: staff first (their outcomes are yesterday's return signals),
    #    then the shared mailbox, then new enrolments, then today's journey steps.
    ctx = load_day(data_dir, store, catalog)
    summary = {
        "date": ctx.day,
        "resolved_by_staff": sum(humans.work_queues(ctx).values()),
        "mailbox_replies_triaged": sum(mailbox.triage_new_replies(ctx).values()),
        "feedback_classified": feedback.classify_new_feedback(ctx),
        **rules.evaluate_plays(ctx),
        **journeys.advance_journeys(ctx),
        "queue_alerts": len(handoff.check_queue_capacity(ctx)),
    }
    # Saved after every day, so the world and the engine's state can never be out of step.
    world.save(truth / "world_state.pkl")
    if verbose:
        print_day(summary)
    return summary


def run_days(
    days: int, data_dir: Path = DATA_DIR, model_dir: Path = MODEL_DIR, verbose: bool = True
) -> list[dict]:
    """Simulate several days in a row, then close the books with a full, tested pipeline run."""
    truth = data_dir / "ground_truth"
    world = World.load(truth / "world_state.pkl")
    summaries = [run_day(data_dir, world, model_dir, verbose) for _ in range(days)]

    issues = json.loads((truth / "injected_issues.json").read_text(encoding="utf-8"))
    write_ground_truth(world, truth, issues)
    # A last full run copies the final engine state into the warehouse and runs every check.
    if verbose:
        print("\n" + get_llm().summary())
        print("Closing the books: full pipeline run with all tests...")
    run_pipeline(data_dir, verbose=False, model_dir=model_dir)
    return summaries


def pending_interventions(store: Store, engine_day: str) -> dict[str, list[dict]]:
    """Everything the engine and the staff did on `engine_day`, grouped by account.

    This is what the simulated customers will react to on the following morning.
    """
    interventions: dict[str, list[dict]] = {}
    for touch in store.rows("SELECT * FROM touches WHERE touch_date = :day", day=engine_day):
        interventions.setdefault(touch["account_id"], []).append(
            {
                "kind": touch["channel"],  # email | in_app | agent
                "play_id": touch["play_id"],
                "contact_id": touch["contact_id"],
                "subject": touch["subject"],
                "outcome": touch["outcome"],
            }
        )
    resolved = store.rows(
        "SELECT * FROM ctas WHERE resolved_on = :day AND play_id IS NOT NULL", day=engine_day
    )
    for cta in resolved:
        interventions.setdefault(cta["account_id"], []).append(
            {"kind": "human", "play_id": cta["play_id"], "outcome": cta["outcome"]}
        )
    return interventions


def print_day(summary: dict) -> None:
    print(
        f"{summary['date']}: entered {summary['entered']}, holdout {summary['holdout']}, "
        f"excluded {summary['excluded']} | emails {summary['emails']}, "
        f"in-app {summary['in_app']}, agent {summary['agent_conversations']}, "
        f"new CTAs {summary['ctas']}, deferred {summary['deferred']} | "
        f"mailbox {summary['mailbox_replies_triaged']}, "
        f"staff resolved {summary['resolved_by_staff']}, goals {summary['goal_reached']}, "
        f"alerts {summary['queue_alerts']}"
    )
