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
    uv run python run.py specs             rebuild docs/play-specs/ from the play config
    uv run python run.py app               open the app (http://localhost:8501)
    uv run python run.py api               start the API (http://localhost:8000/docs)
    uv run python run.py demo              build everything from nothing, ready for the app
    uv run python run.py test              run the tests
    uv run python run.py lint              check code style

This file is the single entry point (see docs/decisions/0006). The Makefile
only forwards to it, for machines that have `make`.
"""

import argparse
import subprocess
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Digital Success OS task runner")
    commands = ["data", "pipeline", "train", "run-day", "run-days", "evals", "experiments"]
    commands += ["specs", "test", "lint"]
    commands += ["app", "api", "demo"]
    parser.add_argument("command", choices=commands)
    parser.add_argument("days", nargs="?", type=int, default=30, help="for run-days: how many")
    parser.add_argument("--profile", default=None, help="config profile, for example: small")
    args = parser.parse_args()

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
    elif args.command == "specs":
        from engine.specs import write_play_specs

        for path in write_play_specs():
            print(f"wrote docs/play-specs/{path.name}")
    elif args.command == "test":
        sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q"]))
    elif args.command == "lint":
        sys.exit(subprocess.call([sys.executable, "-m", "ruff", "check", "."]))
    elif args.command == "app":
        sys.exit(subprocess.call([sys.executable, "-m", "streamlit", "run", "app/main.py"]))
    elif args.command == "api":
        command = [sys.executable, "-m", "uvicorn", "api.main:app", "--port", "8000"]
        sys.exit(subprocess.call(command))
    elif args.command == "demo":
        build_demo(args.days, args.profile)


def build_demo(days: int, profile: str | None = None) -> None:
    """Everything from nothing: data, pipeline, models, simulated days, reports. Then the app."""
    from analytics.train import train_all
    from engine.run import run_days
    from evals.run import run_evals
    from experiments.analyze import analyse
    from ingest.pipeline import run_pipeline
    from synth.generate import generate

    generate(profile=profile)
    run_pipeline()
    train_all()
    run_pipeline(verbose=False)
    run_days(days)
    analyse()
    run_evals()
    print("\nReady. Start the app with: uv run python run.py app")

if __name__ == "__main__":
    main()
