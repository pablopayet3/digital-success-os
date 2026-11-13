"""Write the stored answers of the "Ask the data" example questions (ADR 0028).

Synthetic data, fictional company.

    uv run python scripts/assistant_examples.py --key-file C:/path/to/.env

Claude answers each example question in config/assistant.yaml once, from the data in
data/, and the answers are saved in app/assistant_examples.json. The page shows them as
stored answers, so the examples cost nothing and work without a key.

Run it on the same world the hosted app builds (`run.py demo 10 --profile small`, as in
the Dockerfile), so the stored numbers match what the hosted pages show. It needs
ANTHROPIC_API_KEY, from the environment, this project's .env, or --key-file. The key is
never printed. A full run costs well under a dollar.
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import dotenv_values  # noqa: E402

from agents.assistant import EXAMPLES_FILE, ask, examples  # noqa: E402
from agents.llm import LLM  # noqa: E402
from common.settings import load_settings  # noqa: E402
from common.today import warehouse_today  # noqa: E402


def main(arguments: list[str]) -> None:
    if "--key-file" in arguments:
        key = dotenv_values(arguments[arguments.index("--key-file") + 1]).get("ANTHROPIC_API_KEY")
        if key:
            os.environ["ANTHROPIC_API_KEY"] = key.strip()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("No ANTHROPIC_API_KEY found. Pass --key-file <path to a .env file>.")
    settings = dataclasses.replace(
        load_settings(), offline_mode=False, llm_stand_in=False, stand_in_when_unavailable=False
    )
    # A cache of its own, so these runs never mix with the committed agent responses.
    llm = LLM(settings=settings, cache_dir=Path(tempfile.mkdtemp(prefix="assistant-")))
    answers = []
    for team, questions in examples().items():
        for question in questions:
            answer = ask(question, llm=llm, use_stored=False)
            if not answer.available:
                raise SystemExit(f"No answer for: {question}")
            answers.append({"team": team, **answer.to_dict(), "stored": True})
            print(f"answered ({team}): {question}")
    payload = {
        "note": "Synthetic data, fictional company. Written by scripts/assistant_examples.py.",
        "data_as_of": warehouse_today().isoformat(),
        "written_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "answers": answers,
    }
    EXAMPLES_FILE.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Done. {len(answers)} answers saved in {EXAMPLES_FILE.name}. {llm.summary()}")


if __name__ == "__main__":
    main(sys.argv[1:])
