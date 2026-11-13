"""The voice of the "Ask the data" assistant: short-lived voice sessions, within a budget.

Synthetic data, fictional company. See ADR 0028.

The voice works as in the owner's Alizee applications. The browser talks to the voice
service directly, over a live audio connection, so speech is heard as it is produced and
a person can interrupt. The browser must never hold the real key, so this server asks the
voice service for a short-lived session key and hands only that to the page.

Two rules:
  - The real key (OPENAI_API_KEY) is read from the environment only. It is never logged,
    never returned, and an error body from the voice service is never passed on, because
    such a body can repeat part of the key.
  - Each session is counted against the voice budget before it starts (agents/ledger.py).
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass

import httpx

from agents.ledger import VoiceLedger
from common.config import load_yaml

CLIENT_SECRETS_URL = "https://api.openai.com/v1/realtime/client_secrets"


class VoiceUnavailable(Exception):
    """No voice session can be started. The message is safe to show on screen."""


@dataclass
class VoiceStatus:
    enabled: bool
    reason: str  # one plain sentence for the screen
    budget_usd: float
    spent_usd: float


def config() -> dict:
    return load_yaml("assistant.yaml")["voice"]


def budget_usd() -> float:
    return float(os.environ.get("VOICE_BUDGET_USD", config()["budget_usd"]))


def session_reserve_usd() -> float:
    """What one session may cost at most: its longest length at the assumed price."""
    voice = config()
    return float(voice["max_minutes"]) * float(voice["usd_per_minute"])


def status(ledger: VoiceLedger) -> VoiceStatus:
    budget, spent = budget_usd(), ledger.spent()
    if not os.environ.get("OPENAI_API_KEY"):
        return VoiceStatus(
            False,
            "The voice is turned off here because no key for the voice service has been set.",
            budget,
            spent,
        )
    if spent + session_reserve_usd() > budget:
        return VoiceStatus(
            False,
            f"The voice budget for this demo (${budget:.2f}) is used up. Typing still works.",
            budget,
            spent,
        )
    return VoiceStatus(True, "The voice is available.", budget, spent)


def start_session(ledger: VoiceLedger, transport=None) -> dict:
    """Reserve the session's cost, then ask the voice service for a short-lived key.

    `transport` replaces the HTTP call in tests: a function(url, headers, body) that
    returns (status_code, json_body).
    """
    current = status(ledger)
    if not current.enabled:
        raise VoiceUnavailable(current.reason)
    voice = config()
    body = {"session": {"type": "realtime", "model": voice["model"]}}
    headers = {
        "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
        "Content-Type": "application/json",
    }
    try:
        code, reply = (transport or _post)(CLIENT_SECRETS_URL, headers, body)
    except Exception as error:
        raise VoiceUnavailable("The voice service could not be reached.") from error
    if code != 200 or not isinstance(reply, dict) or "value" not in reply:
        # Never pass the service's error body on: it can repeat part of the key.
        raise VoiceUnavailable(f"The voice service refused to start a session (status {code}).")
    session_id = uuid.uuid4().hex
    ledger.reserve(session_id, session_reserve_usd())
    return {
        "value": reply["value"],
        "expires_at": reply.get("expires_at"),
        "session_id": session_id,
        "model": voice["model"],
    }


def finish_session(ledger: VoiceLedger, session_id: str, seconds: float) -> bool:
    """The page reports how long a session lasted; its reservation shrinks to that."""
    minutes = max(float(seconds), 30.0) / 60  # at least half a minute is counted
    return ledger.finish(session_id, minutes * float(config()["usd_per_minute"]))


def _post(url: str, headers: dict, body: dict) -> tuple[int, dict]:
    response = httpx.post(url, headers=headers, json=body, timeout=15)
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    return response.status_code, payload
