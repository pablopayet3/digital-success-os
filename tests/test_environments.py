"""Tests for environments, secrets and SQL portability (Phase 3b).

Synthetic data, fictional company.
"""

import re

import pytest

from common.paths import ROOT
from common.settings import load_settings, secret

# Functions and syntax that only DuckDB understands. Models must not use them:
# the same SQL has to run on Databricks. Differences belong in dbt/macros/portable.sql.
DUCKDB_ONLY = [
    r"\basof\b",
    r"\bexclude\s*\(",
    r"json_extract",
    r"\blist\s*\(",
    r"string_agg",
    r"date_diff\s*\(",
    r"::",
    r"using sample",
    r"\bpivot\b",
    r"\[\s*\]",
]


def test_default_environment_is_dev_and_offline(monkeypatch):
    monkeypatch.delenv("DSO_ENV", raising=False)
    monkeypatch.delenv("DSO_OFFLINE_MODE", raising=False)
    settings = load_settings()
    assert settings.env == "dev"
    assert settings.warehouse == "duckdb"
    assert settings.dbt_target == "dev"
    assert settings.offline_mode is True
    assert settings.operational_store_url.startswith("sqlite:///")


def test_prod_environment_uses_databricks_and_stays_offline_by_default(monkeypatch):
    monkeypatch.setenv("DSO_ENV", "prod")
    monkeypatch.delenv("DSO_OFFLINE_MODE", raising=False)
    settings = load_settings()
    assert settings.warehouse == "databricks"
    assert settings.dbt_target == "prod"
    assert settings.catalog == "relay"
    assert settings.offline_mode is True


def test_unknown_environment_is_refused(monkeypatch):
    monkeypatch.setenv("DSO_ENV", "staging")
    with pytest.raises(ValueError, match="dev.*prod"):
        load_settings()


def test_llm_limits_can_be_set_from_the_environment(monkeypatch):
    monkeypatch.setenv("MAX_LLM_CALLS_PER_RUN", "25")
    monkeypatch.setenv("LLM_BUDGET_USD", "1.50")
    settings = load_settings()
    assert settings.max_llm_calls_per_run == 25
    assert settings.llm_budget_usd == 1.5
    assert settings.max_agent_conversations_per_run == 50


def test_a_missing_secret_gives_a_clear_message(monkeypatch):
    monkeypatch.delenv("DATABRICKS_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="DATABRICKS_TOKEN is not set"):
        secret("DATABRICKS_TOKEN")


def test_prod_store_url_is_only_needed_when_used(monkeypatch):
    monkeypatch.setenv("DSO_ENV", "prod")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = load_settings()  # loading must not need the secret
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        _ = settings.operational_store_url


def test_env_example_lists_every_secret_and_holds_no_values():
    lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    assignments = [line for line in lines if "=" in line and not line.startswith("#")]
    settings = dict(line.split("=", 1) for line in assignments)
    for name in ("ANTHROPIC_API_KEY", "DATABRICKS_TOKEN", "DATABASE_URL", "LANGSMITH_API_KEY"):
        assert settings[name] == "", f"{name} must be listed and left empty"


def test_env_file_is_ignored_by_git():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in ignored


def test_models_use_no_duckdb_only_sql():
    """The same models must run on DuckDB and Databricks."""
    offenders = []
    for path in sorted((ROOT / "dbt").rglob("*.sql")):
        if "macros" in path.parts or "target" in path.parts:
            continue
        sql = re.sub(r"--.*", "", path.read_text(encoding="utf-8").lower())  # ignore comments
        sql = re.sub(r"\{#.*?#\}", "", sql, flags=re.DOTALL)
        for pattern in DUCKDB_ONLY:
            if re.search(pattern, sql):
                offenders.append(f"{path.name}: {pattern}")
    assert offenders == []
