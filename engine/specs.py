"""Write one specification page per play, from the configuration that actually runs.

Synthetic data, fictional company.

Run with:  uv run python run.py specs

A play spec is the page a play owner signs before launch: trigger and threshold,
audience, what the automation may use, its job, when a person takes over, the test
cases, the success metric and the owner. Specs that are written by hand go stale
the first time someone changes a threshold. These are generated from
config/plays.yaml and config/journeys.yaml, plus the wording in
config/play_specs.yaml, and a test fails if the pages on disk no longer match.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from common.config import load_yaml
from common.paths import ROOT
from engine.catalog import Catalog, Journey, Play, Step, load_catalog

SPEC_DIR = ROOT / "docs" / "play-specs"
EVAL_CASE_DIR = ROOT / "evals" / "cases"
STAGES = {
    "slice": "Slice: 10% of eligible accounts, chosen by hash.",
    "full": "Full test: every eligible account, split into treatment and holdout.",
}


def write_play_specs(folder: Path = SPEC_DIR) -> list[Path]:
    """Write every play's spec. Returns the files written."""
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for play_id, text in render_all().items():
        path = folder / f"{play_id}.md"
        path.write_text(text, encoding="utf-8", newline="\n")
        written.append(path)
    return written


def render_all() -> dict[str, str]:
    catalog, words = load_catalog(), load_yaml("play_specs.yaml")
    return {play.id: render(play, catalog, words) for play in catalog.plays}


def render(play: Play, catalog: Catalog, words: dict) -> str:
    notes = words["plays"][play.id]
    journey = catalog.journeys[play.journey]
    holdout = (
        f"{play.holdout_pct:.0%} of eligible accounts"
        if play.holdout_pct
        else "None. This play is data hygiene, not an experiment."
    )
    lines = [
        f"# Play spec: {play.name}",
        "",
        "Synthetic data, fictional company. Generated from `config/plays.yaml`, "
        "`config/journeys.yaml` and `config/play_specs.yaml` by `uv run python run.py specs`. "
        "Do not edit by hand.",
        "",
        "| | |",
        "|---|---|",
        f"| Play id | `{play.id}` (version {play.version}) |",
        f"| Owner | {play.owner} |",
        f"| Objective | {play.objective} |",
        f"| Priority | {play.priority} of {len(catalog.plays)} (1 claims an account first) |",
        f"| Exclusive | {_exclusive(play)} |",
        f"| Rollout stage | {STAGES[play.rollout_stage]} |",
        f"| Holdout | {holdout} |",
        f"| Re-entry | Not within {play.cooldown_days} days of leaving the play |",
        "",
        "## Trigger and threshold",
        "",
        "An account becomes a candidate when any of these signals fires:",
        "",
        *[f"- `{signal}`: {words['signals'][signal]}" for signal in play.trigger],
        "",
        "## Audience",
        "",
        *_audience(play),
        "",
        "## Exclusions",
        "",
        *[f"- `{rule}`: {words['exclusions'][rule]}" for rule in play.exclusions],
        "",
        "## The job",
        "",
        " ".join(notes["job"].split()),
        "",
        "## Intervention ladder",
        "",
        "| Rung | What happens | Move up when |",
        "|---|---|---|",
        *[
            f"| {rung.tier} | {rung.action} | {' '.join(rung.move_up_when.split())} |"
            for rung in play.intervention_ladder
        ],
        "",
        "## Journey steps",
        "",
        *_journey(journey),
        "",
        "## What the automation may use",
        "",
        *[f"- {item}" for item in notes["automation_may_use"]],
        "",
        "## What it must never do",
        "",
        *[f"- {item}" for item in notes["must_not"]],
        "",
        "## When a person takes over",
        "",
        *_escalation(play, journey, catalog),
        "",
        "## Guardrails from the engine (every play)",
        "",
        *[f"- {item}" for item in words["guardrails"]],
        "",
        "## Test cases",
        "",
        *[f"- {item}" for item in notes["test_cases"]],
        *_eval_cases(play.id),
        "",
        "## Success metric",
        "",
        f"`{play.success_metric['id']}`: {play.success_metric['description']}",
        "",
        f"Measured over {play.measurement_window_days} days from entry, treatment against "
        "holdout, with a confidence interval (`docs/metrics.md`). Decided before launch; "
        "changing it is a new play version.",
        "",
    ]
    return "\n".join(lines)


def _exclusive(play: Play) -> str:
    if play.exclusive:
        return "Yes. An account is in one exclusive play at a time."
    return "No. It may run alongside another play."


def _audience(play: Play) -> list[str]:
    lines = ["- Coverage tier: the pilot segments in `config/rollout.yaml`."]
    if play.audience.get("lifecycle"):
        lines.append(f"- Lifecycle stage: {', '.join(play.audience['lifecycle'])}.")
    else:
        lines.append("- Lifecycle stage: any.")
    if play.audience.get("editions"):
        lines.append(f"- Edition: {', '.join(play.audience['editions'])}.")
    return lines


def _journey(journey: Journey) -> list[str]:
    lines = [f"{number}. {_step(step)}" for number, step in enumerate(journey.steps, start=1)]
    if journey.goal:
        lines += ["", f"Goal (ends the journey at once when reached): `{_goal(journey.goal)}`."]
    return lines


def _step(step: Step) -> str:
    name = f"`{step.id}`"
    if step.type in ("email", "in_app"):
        channel = "Email" if step.type == "email" else "In-app prompt"
        return f"{name}: {channel}, template `{step.template}` ({step.tier})."
    if step.type == "agent":
        return f"{name}: The {step.agent} agent offers a conversation ({step.tier})."
    if step.type == "wait":
        return f"{name}: Wait {step.days} days."
    if step.type == "branch":
        return f"{name}: If `{step.condition}` go to `{step.then}`, otherwise `{step.otherwise}`."
    if step.type == "cta":
        brief = " With an account brief." if step.with_brief else ""
        return (
            f"{name}: Task for a person in queue `{step.queue}`, priority {step.priority}, "
            f"reason `{step.reason_code}`.{brief} The journey waits for the outcome."
        )
    return f"{name}: Exit with reason `{step.reason}`."


def _goal(goal: dict) -> str:
    if goal["metric"] == "signal_cleared":
        return f"signal {goal['signal']} no longer fires"
    return f"{goal['metric']} >= {goal['at_least']}"


def _escalation(play: Play, journey: Journey, catalog: Catalog) -> list[str]:
    """Where this play hands off, read from the journey; plus the agent's hard rules."""
    lines = []
    for step in journey.steps:
        if step.type == "cta":
            queue = catalog.routing["queues"][step.queue]
            lines.append(
                f"- Step `{step.id}`: {step.title}. Queue `{step.queue}` "
                f"(SLA {queue['sla_hours']} hours). Next step for the person: {step.next_step}"
            )
    if any(step.type == "agent" for step in journey.steps):
        lines.append(
            "- During an agent conversation, the hard rules in `agents/escalation.py` hand "
            "off at once: the customer asks for a person; frustration; pricing or upgrade "
            "(to Sales); contract, refund or legal; no help article covers the question; a "
            "tool fails; the same question twice; the model is unavailable. "
            "See `docs/human-fallback.md`."
        )
    if not lines:
        lines.append("- Never. This play has no human rung.")
    lines.append(
        "- What comes back: the person's outcome decides whether the journey resumes, ends "
        "or passes to Sales (`config/routing.yaml`, `outcomes`)."
    )
    return lines


def _eval_cases(play_id: str) -> list[str]:
    """Evaluation cases tagged with this play, read from evals/cases/ (Phase 6)."""
    lines = []
    for path in sorted(EVAL_CASE_DIR.glob("*.yaml")):
        cases = yaml.safe_load(path.read_text(encoding="utf-8")).get("cases", [])
        ids = [case["id"] for case in cases if case.get("play") == play_id]
        if ids:
            lines.append(f"- `evals/cases/{path.name}` ({len(ids)} cases): {', '.join(ids)}")
    return lines
