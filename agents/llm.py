"""The one place that talks to the LLM API, with the cost rules built in.

Synthetic data, fictional company.

Every agent, classifier and judge in this project calls `LLM.call(...)`. Nothing
calls the Anthropic SDK directly. That makes four rules impossible to forget:

  1. Cache everything.  Each response is saved in cache/llm/ under a fingerprint of
                        the exact request. The same request again is read from disk:
                        instant, free, and identical. This is what offline mode replays.
  2. Offline by default. In offline mode a request that is not in the cache is not sent.
                        The caller gets `LLMUnavailable` and takes its fallback (an agent
                        hands off to a human; it never guesses).
  3. Stop at the limit.  A run may make MAX_LLM_CALLS_PER_RUN paid calls and spend
                        LLM_BUDGET_USD. At either limit, `LLMBudgetReached` is raised
                        before the call is made, and the spend is logged.
  4. Models are config.  config/llm.yaml says which model does which job ("role").

Tests and CI pass in a fake `transport`, so they never need a key or a network.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from common.config import load_yaml
from common.paths import ROOT
from common.settings import Settings, load_settings

CACHE_DIR = ROOT / "cache" / "llm"
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMUnavailable(Exception):
    """No answer is available: offline with nothing cached, no key, or the API failed."""


class LLMBudgetReached(LLMUnavailable):
    """The run hit its limit on paid calls or on spend."""


@dataclass
class LLMResponse:
    text: str  # the model's visible reply
    tool_calls: list[dict]  # [{"id", "name", "input"}] when the model asks for tools
    stop_reason: str  # end_turn | tool_use | max_tokens | refusal
    content: list[dict]  # the full reply blocks, to append to the conversation unchanged
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float  # 0 when served from the cache
    cached: bool
    latency_ms: int


@dataclass
class LLM:
    settings: Settings = field(default_factory=load_settings)
    cache_dir: Path = CACHE_DIR
    transport: object = None  # a function(request) -> response dict; None = the real API
    paid_calls: int = 0
    cached_calls: int = 0
    spent_usd: float = 0.0
    log: list = field(default_factory=list)

    def __post_init__(self):
        self.config = load_yaml("llm.yaml")
        if self.settings.llm_stand_in and self.transport is None:
            from agents.stand_in import stand_in_transport

            self.transport = stand_in_transport

    def call(
        self,
        role: str,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        json_schema: dict | None = None,
        purpose: str = "",
    ) -> LLMResponse:
        """Ask the model configured for `role`. See the module docstring for the rules."""
        role_config = self.config["roles"][role]
        request = {
            "model": role_config["model"],
            "max_tokens": role_config["max_tokens"],
            "effort": role_config["effort"],
            "system": system,
            "messages": messages,
            "tools": tools or [],
            "json_schema": json_schema,
            "refusal_fallback": bool(role_config.get("refusal_fallback")),
        }
        key = fingerprint(request)
        cache_file = self.cache_dir / f"{key}.json"

        if cache_file.exists():
            raw = json.loads(cache_file.read_text(encoding="utf-8"))["response"]
            self.cached_calls += 1
            response = self._to_response(raw, cached=True, latency_ms=0)
        else:
            self._check_allowed()
            started = time.time()
            raw = self._send(request)
            response = self._to_response(raw, cached=False, latency_ms=_ms_since(started))
            self.paid_calls += 1
            self.spent_usd += response.cost_usd
            self._save(cache_file, role, purpose, request, raw)

        self.log.append(
            {
                "role": role,
                "purpose": purpose,
                "model": response.model,
                "cached": response.cached,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "cost_usd": round(response.cost_usd, 6),
                "latency_ms": response.latency_ms,
            }
        )
        return response

    @property
    def mode(self) -> str:
        """Where answers come from, in words a screen can show."""
        if self.settings.llm_stand_in:
            return "stand-in (keyword rules, not an LLM)"
        if self.transport is None and self.settings.offline_mode:
            return "offline (replaying cached model responses)"
        return "live (calling the API)"

    def summary(self) -> str:
        """One line for the end of a run: how many calls, how many were free, what it cost."""
        if self.settings.llm_stand_in:
            return (
                f"LLM mode: {self.mode}. {self.paid_calls + self.cached_calls} stand-in "
                "answers, no API calls, $0 spent."
            )
        return (
            f"LLM mode: {self.mode}. "
            f"LLM calls: {self.paid_calls + self.cached_calls} "
            f"({self.cached_calls} from cache, {self.paid_calls} paid), "
            f"spent ${self.spent_usd:.4f} of ${self.settings.llm_budget_usd:.2f}"
        )

    # --- internals -----------------------------------------------------------------------

    def _check_allowed(self) -> None:
        """Refuse a paid call that is not allowed, before it is made."""
        if self.settings.llm_stand_in:
            return  # the stand-in costs nothing and calls nothing
        if self.transport is None and self.settings.offline_mode:
            raise LLMUnavailable("offline mode: no cached response for this request")
        if self.paid_calls >= self.settings.max_llm_calls_per_run:
            raise LLMBudgetReached(f"call limit reached. {self.summary()}")
        if self.spent_usd >= self.settings.llm_budget_usd:
            raise LLMBudgetReached(f"budget reached. {self.summary()}")

    def _send(self, request: dict) -> dict:
        if self.transport is not None:
            return self.transport(request)
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise LLMUnavailable("ANTHROPIC_API_KEY is not set")
        return send_to_anthropic(request)

    def _to_response(self, raw: dict, cached: bool, latency_ms: int) -> LLMResponse:
        blocks = raw.get("content", [])
        usage = raw.get("usage", {})
        return LLMResponse(
            text="\n".join(b["text"] for b in blocks if b.get("type") == "text").strip(),
            tool_calls=[
                {"id": b["id"], "name": b["name"], "input": b["input"]}
                for b in blocks
                if b.get("type") == "tool_use"
            ],
            stop_reason=raw.get("stop_reason", "end_turn"),
            content=blocks,
            model=raw.get("model", ""),
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cost_usd=0.0 if cached else self._cost(raw.get("model", ""), usage),
            cached=cached,
            latency_ms=latency_ms,
        )

    def _cost(self, model: str, usage: dict) -> float:
        """What a response cost, from its token counts and the price list in config/llm.yaml."""
        price_list = self.config["prices_per_million_tokens"]
        prices = price_list.get(model)
        if prices is None:
            if self.settings.llm_stand_in:
                return 0.0  # the rule-based stand-in costs nothing
            # A model with no listed price (for example the fallback model that answers
            # after a refusal). Count it at the highest price we know, so the budget can
            # be over-counted but never under-counted.
            prices = max(price_list.values(), key=lambda price: price["output"])
        input_tokens = (
            usage.get("input_tokens", 0)
            + 1.25 * (usage.get("cache_creation_input_tokens") or 0)  # writing the prompt cache
            + 0.10 * (usage.get("cache_read_input_tokens") or 0)  # reading it back
        )
        output_tokens = usage.get("output_tokens", 0)
        return (input_tokens * prices["input"] + output_tokens * prices["output"]) / 1_000_000

    def _save(self, cache_file: Path, role: str, purpose: str, request: dict, raw: dict) -> None:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        entry = {"role": role, "purpose": purpose, "request": request, "response": raw}
        cache_file.write_text(json.dumps(entry, indent=1), encoding="utf-8")


def fingerprint(request: dict) -> str:
    """A short id that is the same for the same request and different for any other."""
    canonical = json.dumps(request, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:32]


def send_to_anthropic(request: dict) -> dict:
    """One call to the Anthropic Messages API. Returns the response as a plain dictionary."""
    import anthropic  # imported here so offline runs never need the SDK to start

    output_config: dict = {"effort": request["effort"]}
    if request["json_schema"]:
        output_config["format"] = {"type": "json_schema", "schema": request["json_schema"]}
    arguments = {
        "model": request["model"],
        "max_tokens": request["max_tokens"],
        # The system prompt is marked cacheable: repeated calls reuse it at a tenth of the price.
        "system": [
            {"type": "text", "text": request["system"], "cache_control": {"type": "ephemeral"}}
        ],
        "messages": request["messages"],
        "output_config": output_config,
    }
    if request["tools"]:
        arguments["tools"] = request["tools"]

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    try:
        if request["refusal_fallback"]:
            # If the model declines for safety reasons, the API re-runs the same request
            # on a fallback model inside the same call.
            message = client.beta.messages.create(
                betas=[FALLBACK_BETA], fallbacks="default", **arguments
            )
        else:
            message = client.messages.create(**arguments)
    except anthropic.RateLimitError as error:
        raise LLMUnavailable(f"rate limited: {error.message}") from error
    except anthropic.APIStatusError as error:
        raise LLMUnavailable(f"API error {error.status_code}: {error.message}") from error
    except anthropic.APIConnectionError as error:
        raise LLMUnavailable("could not reach the API") from error
    return message.to_dict()


def _ms_since(started: float) -> int:
    return int((time.time() - started) * 1000)


# One shared client per process, so the call and budget limits apply to the whole run.
_shared: LLM | None = None


def get_llm() -> LLM:
    global _shared
    if _shared is None:
        settings = load_settings()
        # The stand-in's answers go to their own folder, never into the cache of real responses.
        folder = ROOT / "cache" / "stand_in" if settings.llm_stand_in else CACHE_DIR
        _shared = LLM(settings, folder)
    return _shared


def set_llm(llm: LLM | None) -> None:
    """Replace the shared client (tests use this to plug in a fake)."""
    global _shared
    _shared = llm
