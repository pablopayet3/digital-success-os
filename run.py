"""Task runner for the Digital Success OS demo. Synthetic data, fictional company.

Usage:
    uv run python run.py data              generate the synthetic world
    uv run python run.py data --profile small
    uv run python run.py pipeline          ingest, build silver and gold, run data tests
    uv run python run.py train             train the churn and expansion models
    uv run python run.py run-day           simulate one day: world, pipeline, engine
    uv run python run.py run-days 30       simulate thirty days
    uv run python run.py evals             score the agents on the evaluation cases
    uv run python run.py experiments       compare every play with its holdout
    uv run python run.py review            write the monthly operating review from the data
    uv run python run.py extracts          write the gold tables as files for a BI tool
    uv run python run.py specs             rebuild docs/play-specs/ from the play config
    uv run python run.py app               open the app (http://localhost:8501)
    uv run python run.py api               start the API (http://localhost:8000/docs)
    uv run python run.py demo              build everything from nothing, ready for the app
    uv run python run.py test              run the tests
    uv run python run.py lint              check code style

Who answers as the model (add to any command):
    (nothing)      real model responses replayed from cache/llm/; no key, no network
    --live         the cache first, then the API, up to the budget; needs a key in .env
    --stand-in     keyword rules, labelled as a stand-in everywhere; no key, no network

This file is the single entry point (see docs/decisions/0006). The Makefile
only forwards to it, for machines that have `make`.
"""

import argparse
import os
import subprocess
import sys

APP_URL = "http://localhost:8501"
COMMANDS = [
    "data", "pipeline", "train", "run-day", "run-days", "evals", "experiments", "review",
    "extracts", "specs", "app", "api", "demo", "test", "lint",
]  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser(description="Digital Success OS task runner")
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("days", nargs="?", type=int, default=30, help="for run-days: how many")
    parser.add_argument("--profile", default=None, help="config profile, for example: small")
    parser.add_argument("--live", action="store_true", help="call the API when not cached")
    parser.add_argument("--stand-in", action="store_true", help="keyword rules play the model")
    parser.add_argument("--no-browser", action="store_true", help="for app: do not open a tab")
    args = parser.parse_args()
    if args.live and args.stand_in:
        parser.error("choose --live or --stand-in, not both")
    choose_who_answers(args.live, args.stand_in)

    if args.command == "data":
        from synth.generate import generate

        generate(profile=args.profile)
    elif args.command == "pipeline":
        from ingest.pipeline import run_pipeline

        sys.exit(0 if run_pipeline() else 1)
    elif args.command == "train":
        from analytics.train import train_all
        from ingest.pipeline import run_pipeline

        train_all()
        # Run the pipeline again so the new scores reach account_daily and the signals.
        print("\nRefreshing scores, lifecycle stages and signals with the new models...")
        sys.exit(0 if run_pipeline(verbose=False) else 1)
    elif args.command == "run-day":
        from engine.run import run_day

        run_day()
    elif args.command == "run-days":
        from engine.run import run_days

        run_days(args.days)
    elif args.command == "evals":
        from evals.run import run_evals

        run_evals()
    elif args.command == "experiments":
        from experiments.analyze import analyse

        analyse()
    elif args.command == "review":
        from experiments.review import write_operating_review

        print(f"wrote {write_operating_review().name}: docs/operating-review.md")
    elif args.command == "extracts":
        from analytics.extracts import write_extracts

        for name, rows in write_extracts().items():
            print(f"wrote exports/bi/{name} ({rows:,} rows)")
    elif args.command == "specs":
        from engine.specs import write_play_specs

        for path in write_play_specs():
            print(f"wrote docs/play-specs/{path.name}")
    elif args.command == "test":
        sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q"]))
    elif args.command == "lint":
        sys.exit(subprocess.call([sys.executable, "-m", "ruff", "check", "."]))
    elif args.command == "app":
        start_app(open_browser=not args.no_browser)
    elif args.command == "api":
        command = [sys.executable, "-m", "uvicorn", "api.main:app", "--port", "8000"]
        sys.exit(subprocess.call(command))
    elif args.command == "demo":
        build_demo(args.days, args.profile)


def start_app(open_browser: bool = True) -> None:
    """Start the app and open it in the browser.

    Streamlit is started "headless" so that a first run does not stop in the terminal to
    ask for an email address. We open the browser tab ourselves a few seconds later.
    """
    import threading
    import webbrowser

    if open_browser:
        threading.Timer(4, lambda: webbrowser.open(APP_URL)).start()
    print(f"Starting the app at {APP_URL} (press Ctrl+C here to stop it)")
    command = [sys.executable, "-m", "streamlit", "run", "app/main.py"]
    command += ["--server.headless", "true", "--browser.gatherUsageStats", "false"]
    sys.exit(subprocess.call(command))


def choose_who_answers(live: bool, stand_in: bool) -> None:
    """Turn --live or --stand-in into the settings the rest of the code reads.

    Set here, before anything else is loaded, so the choice also reaches whatever this
    command starts (the app, the API).
    """
    if live:
        os.environ["DSO_OFFLINE_MODE"] = "false"
        os.environ["DSO_LLM_STAND_IN"] = "false"
    elif stand_in:
        os.environ["DSO_LLM_STAND_IN"] = "true"


def build_demo(days: int, profile: str | None = None) -> None:
    """Everything from nothing: data, pipeline, models, simulated days, reports. Then the app."""
    from analytics.train import train_all
    from engine.run import run_days
    from evals.run import run_evals
    from experiments.analyze import analyse
    from experiments.review import write_operating_review
    from ingest.pipeline import run_pipeline
    from synth.generate import generate

    generate(profile=profile)
    run_pipeline()
    train_all()
    run_pipeline(verbose=False)
    run_days(days)
    analyse()
    run_evals()
    if profile is None:  # the committed review describes the full world, not a small one
        write_operating_review()
    print("\nReady. Start the app with: uv run python run.py app")


if __name__ == "__main__":
    main()
