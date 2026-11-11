"""Simulated staff who work the queues during a simulated day.

Synthetic data, fictional company. In the live demo a real person resolves CTAs
in the Human console. When the simulation runs many days on its own, somebody has
to play the people, or no handoff would ever come back.

Each queue works up to its daily capacity, highest priority first, then by SLA.
Only CTAs created on an earlier day are picked up, so time-to-pickup is at least
a day. The outcome is drawn from config/sim_effects.yaml, deterministically per
CTA, so every run resolves the same task the same way.
"""

from __future__ import annotations

from common.config import load_yaml
from engine.assignment import bucket
from engine.context import DayContext
from engine.handoff import resolve_cta


def work_queues(ctx: DayContext) -> dict[str, int]:
    """Resolve what each team has capacity for today. Returns CTAs resolved per queue."""
    outcome_chances = load_yaml("sim_effects.yaml")["simulated_humans"]
    priorities = ctx.catalog.routing["priorities"]
    resolved = {}

    for queue, settings in ctx.catalog.routing["queues"].items():
        waiting = ctx.store.rows(
            "SELECT * FROM ctas WHERE queue = :queue AND status <> 'resolved' "
            "AND created_on < :today",
            queue=queue,
            today=ctx.day,
        )
        waiting.sort(key=lambda c: (priorities.index(c["priority"]), c["sla_due_on"], c["cta_id"]))
        for cta in waiting[: settings["capacity_per_day"]]:
            outcome = _pick_outcome(cta["cta_id"], outcome_chances[queue])
            resolve_cta(
                ctx.store, ctx.catalog, cta["cta_id"], outcome, ctx.today,
                notes="Resolved by simulated staff.", resolved_by="simulated staff",
            )  # fmt: skip
        resolved[queue] = min(len(waiting), settings["capacity_per_day"])
    return resolved


def _pick_outcome(cta_id: str, chances: dict[str, float]) -> str:
    """Choose an outcome with the configured chances, always the same for the same CTA."""
    position, running_total = bucket(cta_id, "human_outcome"), 0.0
    for outcome, chance in chances.items():
        running_total += chance
        if position < running_total:
            return outcome
    return list(chances)[-1]
