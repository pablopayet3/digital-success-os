"""Store the real model's answers to the Live demo's scripted story, so it replays instantly.

Synthetic data, fictional company.

The hosted demo is built from `run.py demo 10 --profile small` inside the image. Its Live
demo page opens on the customers listed below, and the scripted story asks the agent the
same two questions every time. If the model's answers to that exact conversation are in
cache/llm/, "Run the story" replays them at once, even when the hosted app runs live.

Run it on a copy of that world, with the real model, once after anything changes the
world or the agent's prompt (about 3 cents per customer):

    DSO_DATA_DIR=<a folder built by run.py demo 10 --profile small> \
    DSO_OFFLINE_MODE=false DSO_LLM_STAND_IN=false \
    uv run python scripts/story_answers.py

The new files in cache/llm/ are then committed, and the image carries them.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.llm import get_llm  # noqa: E402
from agents.onboarding import converse, scripted  # noqa: E402
from app import ui  # noqa: E402
from app.demo_story import STORY, demo_accounts  # noqa: E402
from engine.context import records  # noqa: E402

CUSTOMERS = 5  # the first customers in the page's list, which the page opens on


def main() -> None:
    llm = get_llm()
    print(f"LLM mode: {llm.mode}. Data: {ui.data_dir()}")
    for account_id in demo_accounts()[:CUSTOMERS]:
        account = records(
            ui.query(f"SELECT * FROM gold.account_current WHERE account_id = '{account_id}'")
        )[0]
        conversation = converse(account, scripted(STORY))
        print(
            f"{account_id} {account['account_name']}: {conversation.outcome}, "
            f"{len(conversation.llm_log)} model calls"
        )
    print(llm.summary())


if __name__ == "__main__":
    main()
