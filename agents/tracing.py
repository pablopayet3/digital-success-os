"""A record of everything an agent run did, with personal data masked.

Synthetic data, fictional company.

Every agent run produces one trace: what came in, which tools were called and
what they returned, which articles were retrieved, what the model said, how long
it took, what it cost, and the decision (answered or escalated, and why).

Traces are written as JSON files under data/traces/ and shown in the app. When a
LANGSMITH_API_KEY is set they are also sent to LangSmith. Either way, email
addresses and the names of the people in the conversation are masked first: a
trace is for debugging the agent, not for reading customer details.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")


def mask(value, names: list[str]):
    """Replace email addresses and the given names, anywhere inside a value."""
    if isinstance(value, str):
        value = EMAIL.sub("<email>", value)
        for name in names:
            if name:
                value = re.sub(re.escape(name), "<name>", value, flags=re.IGNORECASE)
        return value
    if isinstance(value, dict):
        return {key: mask(item, names) for key, item in value.items()}
    if isinstance(value, list):
        return [mask(item, names) for item in value]
    return value


class Trace:
    def __init__(self, kind: str, account_id: str, day: str, names_to_mask: list[str]):
        self.id = uuid.uuid4().hex[:12]
        self.day = day
        self.names = sorted({n for n in names_to_mask if n}, key=len, reverse=True)
        self.record = {
            "trace_id": self.id,
            "kind": kind,
            "account_id": account_id,
            "simulated_day": day,
            "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "steps": [],
            "decision": None,
        }

    def step(self, name: str, **details) -> None:
        self.record["steps"].append({"step": name, **mask(details, self.names)})

    def finish(self, decision: str, reason: str | None, llm_log: list[dict], folder: Path) -> Path:
        """Close the trace, write it to disk, and return where it was written."""
        self.record["decision"] = {"outcome": decision, "reason": reason}
        self.record["llm_calls"] = len(llm_log)
        self.record["cached_llm_calls"] = sum(1 for call in llm_log if call["cached"])
        self.record["tokens"] = {
            "input": sum(call["input_tokens"] for call in llm_log),
            "output": sum(call["output_tokens"] for call in llm_log),
        }
        self.record["cost_usd"] = round(sum(call["cost_usd"] for call in llm_log), 6)
        self.record["latency_ms"] = sum(call["latency_ms"] for call in llm_log)
        path = folder / self.day / f"{self.id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.record, indent=1), encoding="utf-8")
        send_to_langsmith(self.record)
        return path


def send_to_langsmith(record: dict) -> None:
    """Also send the (already masked) trace to LangSmith, if a key is configured.

    Optional and best-effort: a tracing problem must never break an agent run.
    Not yet run against a real LangSmith account.
    """
    if not os.environ.get("LANGSMITH_API_KEY"):
        return
    try:
        from langsmith import Client  # only needed when a key is set

        Client().create_run(
            name=f"{record['kind']}:{record['account_id']}",
            run_type="chain",
            inputs={"steps": record["steps"][:1]},
            outputs={"decision": record["decision"], "steps": record["steps"]},
            project_name="digital-success-os",
        )
    except Exception:  # noqa: BLE001 (deliberately broad: tracing is never allowed to fail a run)
        pass
