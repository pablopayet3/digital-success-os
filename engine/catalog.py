"""Load the play catalog and the journeys, and check that they make sense.

Synthetic data, fictional company.

Plays are config, not code (config/plays.yaml, config/journeys.yaml,
config/routing.yaml). This module reads them into simple objects and refuses to
start if something is wrong: a play pointing at a journey that does not exist, a
branch jumping to a missing step, a CTA for an unknown queue. Catching a typo
here is much cheaper than discovering it halfway through a run.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from common.config import load_yaml
from common.paths import ROOT

TEMPLATE_DIR = ROOT / "engine" / "templates"
Tier = Literal["digital", "agentic", "human"]
KNOWN_SIGNALS = {
    "activation_stalled", "usage_drop", "seat_pressure", "edition_fit", "cross_product",
    "detractor", "support_friction", "no_valid_admin", "churn_risk_high", "expansion_ready",
}  # fmt: skip
KNOWN_EXCLUSIONS = {
    "already_in_this_play", "in_another_play", "open_escalation", "renewal_in_negotiation",
    "no_emailable_admin", "no_emailable_contact",
}  # fmt: skip


class Step(BaseModel):
    id: str
    type: Literal["email", "in_app", "agent", "wait", "branch", "cta", "exit"]
    tier: Tier | None = None
    template: str | None = None  # email, in_app
    agent: str | None = None  # agent
    days: int | None = None  # wait
    condition: str | None = Field(default=None, alias="if")  # branch
    then: str | None = None
    otherwise: str | None = Field(default=None, alias="else")
    queue: str | None = None  # cta
    priority: str = "normal"
    reason_code: str | None = None
    title: str | None = None
    next_step: str | None = None  # recommended next step for the human
    with_brief: bool = False
    pause_account: bool = False
    reason: str | None = None  # exit


class Journey(BaseModel):
    id: str
    steps: list[Step]
    goal: dict | None = None

    def step(self, step_id: str) -> Step:
        return next(step for step in self.steps if step.id == step_id)

    def after(self, step_id: str) -> str | None:
        """The id of the step that follows, or None at the end of the journey."""
        ids = [step.id for step in self.steps]
        position = ids.index(step_id) + 1
        return ids[position] if position < len(ids) else None


class LadderRung(BaseModel):
    tier: Tier
    action: str
    move_up_when: str


class Play(BaseModel):
    id: str
    name: str
    owner: str
    objective: str
    trigger: list[str]
    audience: dict = {}
    exclusions: list[str] = []
    intervention_ladder: list[LadderRung]
    channel_sequence: list[str]
    journey: str
    priority: int
    exclusive: bool = True
    holdout_pct: float = Field(ge=0, le=1)
    rollout_stage: Literal["slice", "full"]
    success_metric: dict
    version: int
    cooldown_days: int = 60
    measurement_window_days: int = 30


class Catalog(BaseModel):
    plays: list[Play]  # in priority order: the first play to claim an account wins
    journeys: dict[str, Journey]
    routing: dict

    def play(self, play_id: str) -> Play:
        return next(play for play in self.plays if play.id == play_id)


def load_catalog() -> Catalog:
    plays_file = load_yaml("plays.yaml")
    defaults = plays_file.get("defaults", {})
    plays = [Play(**{**defaults, **play}) for play in plays_file["plays"]]
    journeys = {
        journey_id: Journey(id=journey_id, **journey)
        for journey_id, journey in load_yaml("journeys.yaml")["journeys"].items()
    }
    catalog = Catalog(
        plays=sorted(plays, key=lambda play: play.priority),
        journeys=journeys,
        routing=load_yaml("routing.yaml"),
    )
    problems = find_problems(catalog)
    if problems:
        raise ValueError("The play catalog has problems:\n- " + "\n- ".join(problems))
    return catalog


def find_problems(catalog: Catalog) -> list[str]:
    """Everything that is wrong with the configuration, in plain words."""
    problems = []
    priorities = [play.priority for play in catalog.plays]
    if len(set(priorities)) != len(priorities):
        problems.append("two plays share the same priority")

    for play in catalog.plays:
        if play.journey not in catalog.journeys:
            problems.append(f"play {play.id}: journey '{play.journey}' does not exist")
        for signal in play.trigger:
            if signal not in KNOWN_SIGNALS:
                problems.append(f"play {play.id}: unknown trigger signal '{signal}'")
        for rule in play.exclusions:
            if rule not in KNOWN_EXCLUSIONS:
                problems.append(f"play {play.id}: unknown exclusion '{rule}'")

    for journey in catalog.journeys.values():
        ids = [step.id for step in journey.steps]
        if len(set(ids)) != len(ids):
            problems.append(f"journey {journey.id}: two steps share the same id")
        for step in journey.steps:
            where = f"journey {journey.id}, step {step.id}"
            if step.type in ("email", "in_app", "agent", "cta") and step.tier is None:
                problems.append(f"{where}: needs a tier (digital, agentic or human)")
            if step.type in ("email", "in_app"):
                if not (TEMPLATE_DIR / f"{step.template}.md").exists():
                    problems.append(f"{where}: template '{step.template}' not found")
            if step.type == "wait" and not step.days:
                problems.append(f"{where}: a wait needs a number of days")
            if step.type == "branch":
                for target in (step.then, step.otherwise):
                    if target not in ids:
                        problems.append(f"{where}: branch goes to missing step '{target}'")
            if step.type == "cta":
                if step.queue not in catalog.routing["queues"]:
                    problems.append(f"{where}: unknown queue '{step.queue}'")
                if step.reason_code not in catalog.routing["reason_codes"]:
                    problems.append(f"{where}: unknown reason code '{step.reason_code}'")
    return problems
