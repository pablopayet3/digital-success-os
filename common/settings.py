"""Which environment are we in, and what does it use?

Synthetic data, fictional company.

Two environments, same code:
    dev   a laptop: DuckDB, SQLite, offline mode (the safe live demo)
    prod  real services: Databricks, Postgres

Choose with the DSO_ENV environment variable (default: dev). What each environment
uses is described in config/environments.yaml. Secrets are never in a file that is
committed: they come from environment variables, which a local `.env` file can
supply (see .env.example).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from common.config import load_yaml
from common.paths import ROOT

load_dotenv(ROOT / ".env")  # does nothing if the file is not there


@dataclass(frozen=True)
class Settings:
    env: str  # dev | prod
    warehouse: str  # duckdb | databricks
    dbt_target: str
    operational_store: str  # a database URL, or "env:NAME" to read it from a variable
    offline_mode: bool  # True = replay cached LLM responses, never call the API
    llm_stand_in: bool  # True = a rule-based stand-in plays the model (agents/stand_in.py)
    catalog: str | None  # Unity Catalog name (prod)
    landing_volume: str | None  # where landing files are uploaded (prod)
    max_llm_calls_per_run: int
    llm_budget_usd: float
    max_agent_conversations_per_run: int

    @property
    def operational_store_url(self) -> str:
        """The database URL of the operational store (resolved only when it is needed)."""
        url = self.operational_store
        if url.startswith("env:"):
            url = secret(url.removeprefix("env:"))
        # Hosts hand out addresses that start with postgres:// or postgresql://. We use
        # the psycopg driver, so the address is rewritten to name it.
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url.removeprefix(prefix)
        return url


def load_settings() -> Settings:
    config = load_yaml("environments.yaml")
    env = os.environ.get("DSO_ENV", "dev")
    if env not in ("dev", "prod"):
        raise ValueError(f"DSO_ENV must be 'dev' or 'prod', not '{env}'")
    chosen, limits = config[env], config["llm_limits"]
    # The catalog can be overridden (DATABRICKS_CATALOG) for a workspace where a new
    # catalog cannot be created. The landing volume always lives inside that catalog.
    catalog = os.environ.get("DATABRICKS_CATALOG") or chosen.get("catalog")

    return Settings(
        env=env,
        warehouse=chosen["warehouse"],
        dbt_target=chosen["dbt_target"],
        # DSO_OPERATIONAL_STORE lets one part be swapped alone, for example DuckDB as the
        # warehouse with Postgres as the store (the CI job that tests Postgres does this).
        operational_store=os.environ.get("DSO_OPERATIONAL_STORE", chosen["operational_store"]),
        offline_mode=_flag("DSO_OFFLINE_MODE", chosen["offline_mode"]),
        llm_stand_in=_flag("DSO_LLM_STAND_IN", chosen.get("llm_stand_in", False)),
        catalog=catalog,
        landing_volume=f"/Volumes/{catalog}/bronze/landing" if catalog else None,
        max_llm_calls_per_run=int(_override("MAX_LLM_CALLS_PER_RUN", limits)),
        llm_budget_usd=float(_override("LLM_BUDGET_USD", limits)),
        max_agent_conversations_per_run=int(_override("MAX_AGENT_CONVERSATIONS_PER_RUN", limits)),
    )


def secret(name: str) -> str:
    """Read a secret from the environment, with a clear message when it is missing."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"{name} is not set. Put it in your .env file (see .env.example) "
            "or set it as an environment variable. Never commit it."
        )
    return value


def _flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    return default if value is None else value.strip().lower() in ("1", "true", "yes")


def _override(name: str, limits: dict):
    return os.environ.get(name, limits[name.lower()])
