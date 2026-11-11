"""The simulated world, moved forward one day at a time.

Synthetic data, fictional company (Lumen Labs / Relay).

`World.step()` produces one day of everything: product events, seat counts,
tickets, NPS responses, emails and replies. History is just many steps in a
row. From Phase 4 the engine calls `step()` once per simulated day and passes
in the touches it delivered, so customers can react to plays
(see docs/decisions/0005).
"""

from __future__ import annotations

import pickle
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from faker import Faker

from common.config import load_yaml
from synth import behavior, interactions, reactions
from synth.accounts import build_population


class DayOutput:
    """The product events produced on one simulated day."""

    def __init__(self, day: date):
        self.date = day
        self.events: list[dict] = []

    def add(self, account_id: str, user: str, event_name: str, properties: dict) -> None:
        self.events.append(
            {
                "event_id": "",  # filled in at the end of the day
                "occurred_at": "",
                "account_id": account_id,
                "user_id": user,
                "event_name": event_name,
                "properties": properties,
            }
        )


class World:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.seed: int = cfg["seed"]
        self.start_date: date = cfg["calendar"]["start_date"]
        self.day_index = 0  # number of days simulated so far
        self._counters: dict[str, int] = {}

        self.accounts: list = []
        # Everything that has happened so far, as plain rows ready to be written to files.
        self.backfill_events: list[dict] = []
        self.opportunities: list[dict] = []
        self.tickets: list[dict] = []
        self.nps: list[dict] = []
        self.email_sends: list[dict] = []
        self.mailbox: list[dict] = []
        self.license_rows: list[dict] = []
        # Answer keys. These go to data/ground_truth/, never to the landing files.
        self.hidden_rows: list[dict] = []
        self.mailbox_labels: list[dict] = []
        self.ticket_labels: list[dict] = []
        self.interventions_log: list[dict] = []

        self.help_decay: float = load_yaml("sim_effects.yaml")["help_decay_per_day"]

        fake = Faker("en_US")
        fake.seed_instance(self.seed)
        build_population(self, np.random.default_rng([self.seed, 0]), fake)
        self._by_id = {account.account_id: account for account in self.accounts}

    def account(self, account_id: str):
        return self._by_id.get(account_id)

    # --- Time ------------------------------------------------------------------------

    @property
    def today(self) -> date:
        """The next day to be simulated."""
        return self.start_date + timedelta(days=self.day_index)

    @property
    def last_day(self) -> date:
        """The most recent day that has been simulated."""
        return self.today - timedelta(days=1)

    def step(self, interventions: dict | None = None) -> DayOutput:
        """Simulate one day and return its product events.

        `interventions` maps account_id to the touches the engine delivered the
        day before (emails, in-app prompts, agent conversations, human follow-ups).
        Customers react to them first (synth/reactions.py), then live their day.
        """
        today = self.today
        # The randomness for a day depends only on (seed, day number), so any day can be
        # regenerated on its own and always comes out the same.
        rng = np.random.default_rng([self.seed, 1, self.day_index])
        out = DayOutput(today)
        if interventions:
            self.interventions_log.append({"date": today, "interventions": interventions})
            reactions.apply_interventions(self, interventions, today, rng)

        for account in self.accounts:
            if account.contract_start > today or account.status != "active":
                continue  # not a customer yet, or already churned
            behavior.simulate_account_day(self, account, today, rng, out)
            interactions.simulate_account_interactions(self, account, today, rng)
            self.license_rows.append(
                {
                    "date": today,
                    "account_id": account.account_id,
                    "edition": account.edition,
                    "seats_licensed": account.seats_licensed,
                    "seats_assigned": account.seats_assigned,
                }
            )
            self.hidden_rows.append(
                {
                    "date": today,
                    "account_id": account.account_id,
                    "momentum": round(account.momentum, 4),
                    "in_friction": account.friction_days_left > 0,
                    "churn_hazard": round(behavior.churn_hazard(account, today), 6),
                }
            )
        interactions.send_campaign_emails(self, today, rng)

        self._stamp_events(out, rng)
        self.day_index += 1
        return out

    # --- Helpers used by the other synth modules -----------------------------------------

    def next_id(self, prefix: str) -> str:
        """Running ids per kind of record: C000001 (contact), T000001 (ticket), and so on."""
        self._counters[prefix] = self._counters.get(prefix, 0) + 1
        return f"{prefix}{self._counters[prefix]:06d}"

    def add_opportunity(
        self, account, kind: str, name: str, stage: str, amount: int,
        created_at: date, close_date: date,
    ) -> dict:  # fmt: skip
        opportunity = {
            "opportunity_id": self.next_id("O"),
            "account_id": account.account_id,
            "type": kind,  # new_business | renewal | expansion
            "name": name,
            "stage": stage,  # open | negotiation | closed_won | closed_lost
            "amount": amount,
            "created_at": created_at,
            "close_date": close_date,
            "owner": account.account_owner,
            "source": "sales_rep",  # digital plays add their own source from Phase 4
        }
        self.opportunities.append(opportunity)
        return opportunity

    def add_backfill_event(self, account, user: str, name: str, day: date, props: dict) -> None:
        """An event from before the first simulated day (setup that already happened)."""
        n = len(self.backfill_events) + 1
        self.backfill_events.append(
            {
                "event_id": f"ev-backfill-{n:06d}",
                "occurred_at": f"{day.isoformat()}T12:00:00Z",
                "account_id": account.account_id,
                "user_id": user,
                "event_name": name,
                "properties": props,
            }
        )

    def _stamp_events(self, out: DayOutput, rng) -> None:
        """Give every event of the day an id and a time between 06:00 and 22:00 UTC."""
        day = out.date.isoformat()
        compact = day.replace("-", "")
        seconds = rng.integers(6 * 3600, 22 * 3600, size=len(out.events)).tolist()
        for n, (event, s) in enumerate(zip(out.events, seconds, strict=True), start=1):
            event["event_id"] = f"ev-{compact}-{n:06d}"
            event["occurred_at"] = f"{day}T{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}Z"

    # --- Save and resume -----------------------------------------------------------------

    def save(self, path: Path) -> None:
        """Save the whole world so a later run can continue from the same day."""
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @staticmethod
    def load(path: Path) -> World:
        with open(path, "rb") as f:
            return pickle.load(f)
