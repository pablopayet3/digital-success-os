"""The LLM used by the tests: the rule-based stand-in, with a record of every request.

Synthetic data, fictional company. Tests never need a key, a network or money.
The rules themselves live in agents/stand_in.py, because the demo can use them
too (clearly labelled). Here we only add what tests need: a list of the requests
received, and responses priced like the real model so the budget tests mean something.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from agents.llm import LLM
from agents.stand_in import stand_in_transport
from common.settings import load_settings

calls: list[dict] = []  # every request the fake received, for tests to inspect


def fake_llm(cache_dir: Path, **limits) -> LLM:
    """An LLM client wired to the fake, online, with generous limits unless told otherwise."""
    settings = dataclasses.replace(
        load_settings(),
        offline_mode=False,
        llm_stand_in=False,
        max_llm_calls_per_run=limits.get("max_calls", 100_000),
        llm_budget_usd=limits.get("budget", 1_000.0),
        max_agent_conversations_per_run=limits.get("max_conversations", 100_000),
    )
    return LLM(settings=settings, cache_dir=cache_dir, transport=fake_transport)


def fake_transport(request: dict) -> dict:
    calls.append(request)
    response = stand_in_transport(request)
    # Report the model that was asked for, so the response is priced like a real one.
    return {**response, "model": request["model"]}
