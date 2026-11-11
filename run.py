"""Task runner for the Digital Success OS demo. Synthetic data, fictional company.

Usage:
    uv run python run.py data              generate the synthetic world
    uv run python run.py data --profile small
    uv run python run.py pipeline          ingest, build silver and gold, run data tests
    uv run python run.py train             train the churn and expansion models
    uv run python run.py test              run the tests
    uv run python run.py lint              check code style

This file is the single entry point (see docs/decisions/0006). The Makefile
only forwards to it, for machines that have `make`.
"""

import argparse
import subprocess
import sys

# Commands that later phases will deliver, and the phase that delivers them.
LATER = {"run-day": 4, "run-days": 4, "demo": 7, "app": 7}


def main() -> None:
    parser = argparse.ArgumentParser(description="Digital Success OS task runner")
    commands = ["data", "pipeline", "train", "test", "lint", *LATER]
    parser.add_argument("command", choices=commands)
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
    elif args.command == "test":
        sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q"]))
    elif args.command == "lint":
        sys.exit(subprocess.call([sys.executable, "-m", "ruff", "check", "."]))
    else:
        print(f"'{args.command}' arrives in Phase {LATER[args.command]}.")


if __name__ == "__main__":
    main()
