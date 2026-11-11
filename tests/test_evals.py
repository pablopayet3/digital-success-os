"""Tests for the evaluation suite and the experiment analysis (Phase 6).

Synthetic data, fictional company. The evals run here against the stand-in model,
so these tests check the harness (cases load, checks catch what they should, the
report is written), not the quality of a real model's answers.
"""

import math

import pytest

from agents.onboarding import converse, scripted
from engine.catalog import load_catalog
from evals.run import (
    check_conversation,
    eval_account,
    load_cases,
    mailbox_accuracy,
    run_agent_case,
    run_brief_case,
    run_evals,
    tally,
)
from experiments.analyze import (
    analyse,
    sample_ratio_check,
    smallest_detectable_lift,
    two_proportions,
)

# --- Evals -----------------------------------------------------------------------------------


def test_there_are_enough_cases_and_every_id_is_unique():
    cases = load_cases("onboarding_agent") + load_cases("mailbox") + load_cases("briefs")
    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids)) and 30 <= len(ids) <= 50


def test_every_agent_case_names_a_real_play_and_account():
    plays = {play.id for play in load_catalog().plays}
    for case in load_cases("onboarding_agent"):
        assert case["play"] in plays
        assert eval_account(case["account"])["account_name"]


def test_every_category_of_hard_rule_has_a_case():
    categories = {case["category"] for case in load_cases("onboarding_agent")}
    assert {"pricing", "contract", "person", "frustration", "not_in_docs", "failure"} <= categories


def test_a_pricing_case_passes_only_because_the_agent_model_was_never_asked():
    case = next(c for c in load_cases("onboarding_agent") if c["id"] == "onb-17-price-of-seats")
    result = run_agent_case(case, "v2")
    assert result["status"] == "passed" and result["reason_code"] == "pricing_contract_legal"


def test_the_checks_catch_a_wrong_outcome_and_a_forbidden_phrase():
    conversation = converse(
        eval_account("team_not_invited"), scripted(["How do I invite my team?"])
    )
    conversation.transcript.append({"role": "agent", "text": "That will be $12 per seat."})
    expect = {"outcome": "escalated", "must_not_match": [r"[$€£]\s?\d"]}
    failed = [name for name, passed, _ in check_conversation(expect, conversation) if not passed]
    assert failed == ["outcome", "never says"]


def test_a_brief_case_checks_numbers_against_the_account():
    result = run_brief_case(load_cases("briefs")[0])
    assert result["status"] == "passed"


def test_the_eval_run_writes_a_report_that_says_who_answered(simulated, tmp_path):
    _, data_dir = simulated
    results = run_evals(data_dir, tmp_path, verbose=False)
    report = (tmp_path / "eval-report.md").read_text(encoding="utf-8")
    assert (tmp_path / "eval-results.json").exists()
    assert "Answers produced by" in report and "Confusion matrix" in report
    # The test model is not labelled as a stand-in, so the cases that need a real language
    # model are run and may fail. Nothing else may.
    cases = load_cases("onboarding_agent") + load_cases("mailbox") + load_cases("briefs")
    needs_model = {case["id"] for case in cases if case.get("needs_model")}
    groups = [*results["agent"].values(), results["mailbox_cases"], results["briefs"]]
    failed = {result["id"] for group in groups for result in group if result["status"] == "failed"}
    assert failed <= needs_model, f"unexpected failures: {sorted(failed - needs_model)}"
    assert all(counts["run"] > 0 for counts in results["totals"].values())
    assert set(results["agent"]) == {"v1", "v2"}  # both prompt versions ran on the same cases


def test_mailbox_accuracy_is_scored_against_the_simulators_labels(simulated):
    _, data_dir = simulated
    accuracy = mailbox_accuracy(data_dir, sample=40)
    assert accuracy["scored"] == 40 and 0.5 < accuracy["accuracy"] <= 1
    assert sum(sum(row.values()) for row in accuracy["matrix"].values()) == 40


def test_tally_leaves_skipped_cases_out_of_the_pass_rate():
    counts = tally([{"status": "passed"}, {"status": "failed"}, {"status": "skipped"}])
    assert (counts["run"], counts["pass_rate"]) == (2, 0.5)


# --- Experiment statistics ---------------------------------------------------------------------


def test_a_large_clear_difference_is_significant_and_a_small_sample_is_not():
    clear = two_proportions(60, 100, 30, 100)
    assert clear["lift"] == pytest.approx(0.30) and clear["p_value"] < 0.001
    assert clear["ci_low"] > 0
    noisy = two_proportions(6, 10, 3, 10)
    assert noisy["p_value"] > 0.05 and noisy["ci_low"] < 0 < noisy["ci_high"]


def test_no_difference_gives_a_p_value_of_one():
    same = two_proportions(20, 100, 20, 100)
    assert same["lift"] == 0 and same["p_value"] == pytest.approx(1.0)


def test_the_split_check_flags_a_lopsided_holdout():
    assert sample_ratio_check(500, 500, 0.5)["ok"]
    assert sample_ratio_check(260, 240, 0.5)["ok"]  # ordinary chance
    assert not sample_ratio_check(600, 400, 0.5)["ok"]  # something is filtering one group
    assert sample_ratio_check(800, 200, 0.2)["ok"]  # an 80/20 design, as designed


def test_more_accounts_means_a_smaller_lift_can_be_detected():
    small, large = smallest_detectable_lift(30, 30, 0.2), smallest_detectable_lift(300, 300, 0.2)
    assert large < small and math.isclose(small / large, math.sqrt(10), rel_tol=0.01)


def test_the_analysis_covers_every_play_and_writes_results(simulated, tmp_path):
    _, data_dir = simulated
    results = analyse(data_dir, tmp_path, verbose=False)
    plays = {play.id: play for play in load_catalog().plays}
    assert {result["play_id"] for result in results["plays"]} == set(plays)
    for result in results["plays"]:
        assert result["metric"] == plays[result["play_id"]].success_metric["id"]
        assert result["verdict"] and result["recommendation"]
    report = (tmp_path / "experiment-report.md").read_text(encoding="utf-8")
    assert "This is a simulation" in report and "Recommended decisions" in report


def test_every_success_metric_in_the_play_config_exists_in_the_warehouse(simulated):
    import duckdb

    from ingest.load import warehouse_path

    _, data_dir = simulated
    con = duckdb.connect(str(warehouse_path(data_dir)))
    columns = {row[0] for row in con.execute("DESCRIBE gold.metrics_play_outcomes").fetchall()}
    arms = con.execute("SELECT DISTINCT arm FROM gold.metrics_play_outcomes").fetchall()
    con.close()
    assert {play.success_metric["id"] for play in load_catalog().plays} <= columns
    assert {arm for (arm,) in arms} == {"treatment", "holdout"}
