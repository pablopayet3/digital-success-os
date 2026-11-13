"""Record the guided tour: one audio file per stop, in the voice named in config/tour.yaml.

Synthetic data, fictional company. Run it once after the tour's words change:

    uv run python scripts/tour_voice.py
    uv run python scripts/tour_voice.py --key-file C:/path/to/another/.env

The first form reads OPENAI_API_KEY from the environment or from this project's .env.
The second reads it from another .env file, without copying it anywhere.

For each stop that has no recording yet, the script asks a text-to-speech service to read
the stop's words, and saves the result in app/tour_audio/ under a name made from those
words. A stop whose words have not changed is not recorded again, so a second run costs
nothing. Recordings of words that no longer exist are deleted.

This is the one place the project uses a second paid service, at the owner's request
(ADR 0025). A full recording costs well under a dollar. Running the app costs nothing: the
app only plays the files.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import dotenv_values  # noqa: E402

from app.tour import AUDIO, audio_file, spoken, stops  # noqa: E402
from common.config import load_yaml  # noqa: E402
from common.paths import ROOT  # noqa: E402

SPEECH_URL = "https://api.openai.com/v1/audio/speech"


def find_key(key_file: str | None) -> str:
    """The key: from the file named on the command line, or the environment, or .env here."""
    places = [dotenv_values(key_file)] if key_file else [os.environ, dotenv_values(ROOT / ".env")]
    for place in places:
        key = (place.get("OPENAI_API_KEY") or "").strip()
        if key:
            return key
    raise SystemExit(
        "No OPENAI_API_KEY found. Put it in .env, or pass --key-file <path to a .env file>."
    )


def record(text: str, voice: dict, key: str) -> bytes:
    """Ask the service to read one stop aloud. Returns the audio as MP3 bytes."""
    body = {
        "model": voice["model"],
        "voice": voice["name"],
        "input": text,
        "instructions": voice["manner"].strip(),
        "response_format": "mp3",
    }
    request = urllib.request.Request(
        SPEECH_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        # Say what the service answered, never the key.
        detail = error.read().decode("utf-8", errors="replace")[:300]
        raise SystemExit(f"The speech service refused ({error.code}): {detail}") from error


def main(arguments: list[str]) -> None:
    key_file = arguments[arguments.index("--key-file") + 1] if "--key-file" in arguments else None
    voice = load_yaml("tour.yaml")["voice"]
    key = find_key(key_file)
    AUDIO.mkdir(exist_ok=True)

    wanted, made, characters = set(), 0, 0
    for number, stop in enumerate(stops(), start=1):
        target = audio_file(stop)
        wanted.add(target.name)
        if target.exists():
            continue
        text = spoken(stop)
        target.write_bytes(record(text, voice, key))
        made, characters = made + 1, characters + len(text)
        print(f"recorded stop {number}: {stop['title']}")

    stale = [file for file in AUDIO.glob("*.mp3") if file.name not in wanted]
    for file in stale:
        file.unlink()
    print(
        f"Done. {made} recorded ({characters:,} characters sent), "
        f"{len(wanted) - made} already there, {len(stale)} old recordings removed."
    )


if __name__ == "__main__":
    main(sys.argv[1:])
