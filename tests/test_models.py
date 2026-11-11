"""Tests for the health score, lifecycle stage, signals and models (Phase 3).

Synthetic data, fictional company.
"""

import pytest

from analytics.features import FEATURE_PHRASES, FEATURES
from analytics.score import NOT_A_REASON
from analytics.train import pick_snapshot_days
from common.config import load_yaml
from common.warehouse import open_warehouse

LIFECYCLE_STAGES = {"onboarding", "adopting", "mature", "expansion", "renewal", "at_risk"}
HIDDEN_NAMES = {"engagement", "fit", "growth", "momentum", "setup_drive", "team_size", "setback"}


def test_health_weights_add_up_to_one():
    weights = load_yaml("health.yaml")["weights"]
    assert sum(weights.values()) == pytest.approx(1.0)
    assert set(weights) == {"adoption", "engagement", "sentiment", "support", "commercial"}


def test_health_score_is_the_weighted_average_of_its_components(warehouse):
    weights = load_yaml("health.yaml")["weights"]
    rows = warehouse.execute(
        """
        SELECT health_score, health_adoption, health_engagement, health_sentiment,
               health_support, health_commercial
        FROM gold.int_account_daily_health USING SAMPLE 200
        """
    ).fetchall()
    for score, adoption, engagement, sentiment, support, commercial in rows:
        expected = (
            weights["adoption"] * adoption
            + weights["engagement"] * engagement
            + weights["sentiment"] * sentiment
            + weights["support"] * support
            + weights["commercial"] * commercial
        )
        assert score == pytest.approx(expected, abs=0.06)
        assert 0 <= score <= 100


def distinct(con, column: str, table: str) -> set:
    """The different values of one column."""
    return {row[0] for row in con.execute(f"SELECT DISTINCT {column} FROM {table}").fetchall()}


def test_every_account_day_has_one_lifecycle_stage(warehouse):
    stages = distinct(warehouse, "lifecycle_stage", "gold.account_daily")
    assert stages <= LIFECYCLE_STAGES
    assert {"onboarding", "adopting"} <= stages


def test_lifecycle_precedence(scored_warehouse):
    con = scored_warehouse
    # Rule 1 beats everything: a high churn score always means at_risk.
    wrong = con.execute(
        """
        SELECT count(*) FROM gold.account_daily
        WHERE churn_risk_high AND lifecycle_stage <> 'at_risk'
        """
    ).fetchone()[0]
    assert wrong == 0
    # Rule 3: a brand-new account that is neither at risk nor in renewal is onboarding.
    stages = con.execute(
        """
        SELECT DISTINCT lifecycle_stage FROM gold.account_daily
        WHERE account_age_days < 30 AND NOT churn_risk_high AND days_to_renewal > 90
          AND NOT (coalesce(mau_prior_30d, 0) >= 3 AND mau_30d <= 0.5 * mau_prior_30d)
        """
    ).fetchall()
    assert stages == [("onboarding",)]


def test_signals_match_their_rules(warehouse):
    stalled_signals, stalled_rule = warehouse.execute(
        """
        SELECT
            (SELECT count(*) FROM gold.signals WHERE signal_id = 'activation_stalled'),
            (SELECT count(*) FROM gold.account_daily
             WHERE account_age_days >= 7 AND prerequisite_closure_pct < 0.5)
        """
    ).fetchone()
    assert stalled_signals == stalled_rule > 0

    pressure_signals, pressure_rule = warehouse.execute(
        """
        SELECT
            (SELECT count(*) FROM gold.signals WHERE signal_id = 'seat_pressure'),
            (SELECT count(*) FROM gold.account_daily WHERE seat_utilisation >= 0.9)
        """
    ).fetchone()
    assert pressure_signals == pressure_rule > 0


def test_pipeline_works_before_any_model_is_trained(untrained_summary):
    """No model yet: scores are empty, model signals do not fire, everything else does."""
    assert untrained_summary["scored"] == 0
    assert untrained_summary["flagged"] == 0
    assert "activation_stalled" in untrained_summary["signals"]
    assert not untrained_summary["signals"] & {"churn_risk_high", "expansion_ready"}


def test_features_never_use_hidden_ground_truth():
    assert not set(FEATURES) & HIDDEN_NAMES


def test_models_train_on_observed_outcomes_and_test_later_in_time(trained, scored_warehouse):
    metrics, data_dir, _ = trained
    warehouse = open_warehouse(data_dir)
    test_day, train_days = pick_snapshot_days(warehouse, load_yaml("models.yaml"))
    warehouse.close()
    assert all(day < test_day for day in train_days)
    unobserved = scored_warehouse.execute(
        """
        SELECT count(*) FROM gold.fct_outcome_labels
        WHERE snapshot_date = ? AND NOT outcome_observed
        """,
        [test_day],
    ).fetchone()[0]
    assert unobserved == 0
    for name in ("churn", "expansion"):
        assert metrics[name]["test_day"] == str(test_day)
        assert metrics[name]["logistic"]["auc"] > 0.55  # clearly better than a coin flip


def test_flags_follow_team_capacity(scored_warehouse):
    capacity = load_yaml("models.yaml")
    for flag, name in (("churn_risk_high", "churn"), ("expansion_ready", "expansion")):
        flagged = scored_warehouse.execute(
            f"""
            SELECT count(*) FROM gold.account_current
            WHERE {flag} AND coverage_tier = 'uncovered'
            """
        ).fetchone()[0]
        limit = capacity[name]["capacity_accounts"]
        assert limit <= flagged <= limit + 3  # ties at the cut-off can add a few


def test_every_flagged_account_has_a_plain_word_reason(scored_warehouse):
    rows = scored_warehouse.execute(
        "SELECT churn_top_reasons FROM gold.account_current WHERE churn_risk_high"
    ).fetchall()
    assert rows
    # Both phrases of every feature that must never be offered as a reason.
    not_reasons = {phrase for name in NOT_A_REASON for phrase in FEATURE_PHRASES[name]}
    for (reasons,) in rows:
        assert reasons
        assert not set(reasons.split(", ")) & not_reasons


def test_model_scores_reach_signals_and_segments(scored_warehouse):
    fired = distinct(scored_warehouse, "signal_id", "gold.signals")
    assert {"churn_risk_high", "expansion_ready"} <= fired
    clusters = distinct(scored_warehouse, "behaviour_cluster", "gold.account_current")
    assert None not in clusters
    assert len(clusters) == load_yaml("models.yaml")["clusters"]


def test_model_cards_are_written(trained):
    _, _, card_dir = trained
    for name in ("churn", "expansion"):
        card = (card_dir / f"{name}.md").read_text(encoding="utf-8")
        assert "Threshold: chosen by capacity" in card
        assert "Known limitations" in card
