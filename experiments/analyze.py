"""Did the plays work? Treatment against holdout, with the uncertainty stated.

Synthetic data, fictional company.

Run with:  uv run python run.py experiments

For every play, the accounts that received it (treatment) are compared with the
accounts that qualified but were held back (holdout), on the success metric the
play declared before launch. The outcomes come from the warehouse table
gold.metrics_play_outcomes, which dbt builds from telemetry, the CRM and the
operational store: the same route a real result would take.

For each play the report gives:

  - the rate in each group and the difference (the lift), with a 95% interval;
  - a two-proportion z-test (how likely is a gap this large if the play did nothing);
  - a sample-ratio check (did the split come out as designed; if not, do not read it);
  - the smallest lift this sample could have detected, so "no effect found" is not
    mistaken for "no effect";
  - results by weekly cohort and by rung of the intervention ladder;
  - retained revenue and expansion revenue, treatment against holdout;
  - a recommendation: scale, keep testing, or stop.

Honest framing: this is a simulation. Any lift comes from the assumptions in
config/sim_effects.yaml. What the demo shows is the measurement system, not a result.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from common.config import load_yaml
from common.paths import DATA_DIR, ROOT
from common.warehouse import open_warehouse
from engine.catalog import Play, load_catalog

REPORT_DIR = ROOT / "experiments" / "reports"
MIN_DAYS_OBSERVED = 7  # an account that entered yesterday cannot have an outcome yet
MIN_ACCOUNTS_PER_ARM = 20  # below this, a rate is an anecdote
SIGNIFICANCE = 0.05
SRM_ALARM = 0.01  # a split this unlikely by chance means the assignment is broken


# --- the statistics, kept small enough to explain on a whiteboard ---------------------------


def normal_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def two_proportions(successes_t: int, n_t: int, successes_h: int, n_h: int) -> dict:
    """Compare two rates: the lift, its 95% interval, and a two-sided z-test."""
    rate_t, rate_h = successes_t / n_t, successes_h / n_h
    lift = rate_t - rate_h
    # For the test: assume no difference, so both groups share one pooled rate.
    pooled = (successes_t + successes_h) / (n_t + n_h)
    pooled_error = math.sqrt(pooled * (1 - pooled) * (1 / n_t + 1 / n_h))
    z = lift / pooled_error if pooled_error else 0.0
    p_value = 2 * (1 - normal_cdf(abs(z)))
    # For the interval: each group keeps its own rate.
    error = math.sqrt(rate_t * (1 - rate_t) / n_t + rate_h * (1 - rate_h) / n_h)
    return {
        "rate_treatment": rate_t,
        "rate_holdout": rate_h,
        "lift": lift,
        "ci_low": lift - 1.96 * error,
        "ci_high": lift + 1.96 * error,
        "z": z,
        "p_value": p_value,
    }


def sample_ratio_check(n_t: int, n_h: int, holdout_pct: float) -> dict:
    """Did the split come out as designed? A chi-square test with one degree of freedom."""
    total = n_t + n_h
    expected_h, expected_t = total * holdout_pct, total * (1 - holdout_pct)
    chi2 = (n_h - expected_h) ** 2 / expected_h + (n_t - expected_t) ** 2 / expected_t
    p_value = math.erfc(math.sqrt(chi2 / 2))
    return {
        "expected_holdout_share": holdout_pct,
        "observed_holdout_share": n_h / total,
        "p_value": p_value,
        "ok": p_value >= SRM_ALARM,
    }


def smallest_detectable_lift(n_t: int, n_h: int, base_rate: float) -> float:
    """The lift this sample would catch 80% of the time at the 5% level."""
    base = min(max(base_rate, 0.05), 0.95)  # a rate of exactly 0 or 1 would say "anything"
    return (1.96 + 0.84) * math.sqrt(base * (1 - base) * (1 / n_t + 1 / n_h))


# --- one play ---------------------------------------------------------------------------------


def analyse_play(play: Play, outcomes: pd.DataFrame) -> dict:
    """Everything the report says about one play."""
    metric = play.success_metric["id"]
    rows = outcomes[(outcomes["play_id"] == play.id) & (outcomes["play_version"] == play.version)]
    mature = rows[rows["days_observed"] >= MIN_DAYS_OBSERVED]
    treatment, holdout = mature[mature["arm"] == "treatment"], mature[mature["arm"] == "holdout"]
    result = {
        "play_id": play.id,
        "play_name": play.name,
        "owner": play.owner,
        "metric": metric,
        "metric_description": play.success_metric["description"],
        "rollout_stage": play.rollout_stage,
        "holdout_pct": play.holdout_pct,
        "entered_total": int(len(rows)),
        "n_treatment": int(len(treatment)),
        "n_holdout": int(len(holdout)),
        "successes_treatment": int(treatment[metric].sum()),
        "successes_holdout": int(holdout[metric].sum()),
        "median_days_observed": float(mature["days_observed"].median()) if len(mature) else 0.0,
        "ladder": ladder(treatment, metric),
        "cohorts": cohorts(mature, metric),
        "money": money(treatment, holdout),
    }
    if len(treatment):
        result["rate_treatment"] = result["successes_treatment"] / len(treatment)
    if play.holdout_pct and len(treatment) and len(holdout):
        result.update(
            two_proportions(
                result["successes_treatment"],
                len(treatment),
                result["successes_holdout"],
                len(holdout),
            )  # fmt: skip
        )
        # The split is checked on everyone who entered, not only on mature accounts.
        entered = rows["arm"].value_counts()
        result["srm"] = sample_ratio_check(
            int(entered.get("treatment", 0)), int(entered.get("holdout", 0)), play.holdout_pct
        )
        result["detectable_lift"] = smallest_detectable_lift(
            len(treatment), len(holdout), result["rate_holdout"]
        )
        guard = two_proportions(
            int(treatment["retained_30d"].sum()), len(treatment),
            int(holdout["retained_30d"].sum()), len(holdout),
        )  # fmt: skip
        result["guardrail_retention"] = {k: guard[k] for k in ("rate_treatment", "rate_holdout")}
    result["verdict"], result["recommendation"] = verdict(play, result)
    return result


def verdict(play: Play, result: dict) -> tuple[str, str]:
    """What the numbers allow us to say, and what to do next. Rules, not judgement."""
    if not play.holdout_pct:
        rate = result.get("rate_treatment")
        done = f"{rate:.0%} reached the goal" if rate is not None else "no accounts yet"
        return (f"Not an experiment (no holdout): {done}.", "Keep running; track the rate.")
    if "lift" not in result:
        return ("No data yet.", "Keep testing.")
    small = min(result["n_treatment"], result["n_holdout"]) < MIN_ACCOUNTS_PER_ARM
    if not result["srm"]["ok"]:
        return (
            "Do not read this result: the split between treatment and holdout is not the "
            "one designed (sample ratio mismatch).",
            "Find out why before anything else.",
        )
    if small:
        return (
            f"Too early: fewer than {MIN_ACCOUNTS_PER_ARM} accounts in a group.",
            "Keep testing." if play.rollout_stage == "full" else "Keep the slice running.",
        )
    if result["p_value"] < SIGNIFICANCE and result["lift"] > 0:
        return (
            f"Working: +{result['lift']:.0%} on the success metric, unlikely to be chance "
            f"(p = {result['p_value']:.3f}).",
            "Scale: move to the next rollout stage or the next segment, and keep a holdout.",
        )
    if result["p_value"] < SIGNIFICANCE and result["lift"] < 0:
        return (
            f"Harmful: {result['lift']:.0%} on the success metric (p = {result['p_value']:.3f}).",
            "Stop the play and review the journey.",
        )
    return (
        f"No effect detected. This sample could only have shown a lift of about "
        f"{result['detectable_lift']:.0%} or more.",
        "Keep testing until the sample can detect the lift that would justify the play.",
    )


def ladder(treatment: pd.DataFrame, metric: str) -> list[dict]:
    """Treated accounts by the highest rung they reached."""
    rows = []
    for tier in ("digital", "agentic", "human", "none"):
        group = treatment[treatment["highest_tier"] == tier]
        if len(group):
            rows.append(
                {
                    "tier": tier,
                    "accounts": int(len(group)),
                    "successes": int(group[metric].sum()),
                    "rate": float(group[metric].mean()),
                }
            )
    return rows


def cohorts(mature: pd.DataFrame, metric: str) -> list[dict]:
    """Rates by the week accounts entered, so one odd week cannot hide in the average."""
    if mature.empty:
        return []
    frame = mature.assign(
        week=pd.to_datetime(mature["enrolled_on"]).dt.to_period("W").dt.start_time
    )
    rows = []
    for week, group in frame.groupby("week"):
        row = {"week_starting": week.date().isoformat()}
        for arm in ("treatment", "holdout"):
            side = group[group["arm"] == arm]
            row[f"n_{arm}"] = int(len(side))
            row[f"rate_{arm}"] = float(side[metric].mean()) if len(side) else None
        rows.append(row)
    return rows


def money(treatment: pd.DataFrame, holdout: pd.DataFrame) -> dict:
    """Revenue kept and revenue added, per group."""
    result = {}
    for arm, group in (("treatment", treatment), ("holdout", holdout)):
        arr = float(group["arr_at_entry"].sum())
        result[arm] = {
            "arr_at_entry": arr,
            "retained_arr": float(group["retained_arr"].sum()),
            "retained_arr_share": float(group["retained_arr"].sum()) / arr if arr else None,
            "expansion_won": float(group["expansion_amount"].sum()),
            "expansion_per_account": float(group["expansion_amount"].mean())
            if len(group)
            else None,
        }
    return result


# --- all plays, and the report ----------------------------------------------------------------------


def analyse(data_dir: Path = DATA_DIR, report_dir: Path = REPORT_DIR, verbose: bool = True) -> dict:
    """Analyse every play, save the results to the warehouse and write the report."""
    catalog = load_catalog()
    warehouse = open_warehouse(data_dir)
    outcomes = warehouse.query("SELECT * FROM gold.metrics_play_outcomes")
    today = warehouse.query("SELECT max(snapshot_date) AS today FROM gold.account_current")
    handoffs = warehouse.query("SELECT * FROM gold.metrics_handoffs")
    as_of = pd.Timestamp(today["today"][0]).date().isoformat()

    plays = [analyse_play(play, outcomes) for play in catalog.plays]
    results = {
        "as_of": as_of,
        "pilot_segments": load_yaml("rollout.yaml")["segments"],
        "min_days_observed": MIN_DAYS_OBSERVED,
        "plays": plays,
        "handoffs": handoff_summary(handoffs),
    }
    # One row per play in the warehouse, for the app.
    table = pd.DataFrame(
        [
            {
                key: play.get(key)
                for key in (
                    "play_id", "play_name", "metric", "rollout_stage", "holdout_pct",
                    "n_treatment", "n_holdout", "successes_treatment", "successes_holdout",
                    "rate_treatment", "rate_holdout", "lift", "ci_low", "ci_high", "p_value",
                    "detectable_lift", "verdict", "recommendation",
                )
            }
            | {"srm_ok": play.get("srm", {}).get("ok"), "as_of": as_of}
            for play in plays
        ]
    )  # fmt: skip
    warehouse.write_table("gold.experiment_results", table)
    warehouse.close()

    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "experiment-results.json").write_text(
        json.dumps(results, indent=1), encoding="utf-8", newline="\n"
    )
    (report_dir / "experiment-report.md").write_text(
        render_report(results), encoding="utf-8", newline="\n"
    )
    if verbose:
        for play in plays:
            print(f"{play['play_name']}: {play['verdict']}")
        print("Report: experiments/reports/experiment-report.md")
    return results


def handoff_summary(handoffs: pd.DataFrame) -> dict:
    """The human-fallback metrics, over all queues."""
    total, closed = int(handoffs["handoffs"].sum()), int(handoffs["closed"].sum())
    from_agent = handoffs[handoffs["source"] == "agent"]
    not_in_docs = int(from_agent[from_agent["reason_code"] == "not_in_docs"]["handoffs"].sum())
    return {
        "handoffs": total,
        "closed": closed,
        "open_now": int(handoffs["open_now"].sum()),
        "sla_breach_rate": _share(handoffs["sla_breaches"].sum(), total),
        "escalation_conversion": _share(handoffs["converted"].sum(), closed),
        "unnecessary_handoff_rate": _share(handoffs["unnecessary"].sum(), closed),
        "agent_handoffs": int(from_agent["handoffs"].sum()),
        "docs_gap_share": _share(not_in_docs, from_agent["handoffs"].sum()),
    }


def render_report(results: dict) -> str:
    segments = ", ".join(results["pilot_segments"])
    lines = [
        "# Experiment report: plays against their holdouts",
        "",
        "Synthetic data, fictional company. Written by `uv run python run.py experiments`.",
        "",
        f"As of {results['as_of']} (simulated calendar). Pilot segment: {segments}. Accounts "
        f"count once they have been observed for {results['min_days_observed']} days or more.",
        "",
        "> This is a simulation. Customers react to touches according to the assumptions in",
        "> `config/sim_effects.yaml`, so any lift below was put there by those assumptions.",
        "> What this report demonstrates is the measurement: holdouts, a pre-declared metric,",
        "> an interval, a check on the split, and a decision rule.",
        "",
        "## Summary",
        "",
        "| Play | Success metric | Treatment | Holdout | Lift (95% interval) | p | Verdict |",
        "|---|---|---|---|---|---|---|",
    ]
    for play in results["plays"]:
        lines.append(
            f"| {play['play_name']} | {play['metric']} | {_rate(play, 'treatment')} | "
            f"{_rate(play, 'holdout')} | {_lift(play)} | {_p(play)} | {play['verdict']} |"
        )
    lines += ["", "## Recommended decisions", ""]
    lines += [f"- **{play['play_name']}**: {play['recommendation']}" for play in results["plays"]]

    for play in results["plays"]:
        lines += [
            "",
            f"## {play['play_name']}",
            "",
            f"Owner: {play['owner']}. Stage: {play['rollout_stage']}. "
            f"Success metric: {play['metric_description']}",
            "",
            f"- Entered so far: {play['entered_total']} accounts "
            f"({play['n_treatment']} treatment and {play['n_holdout']} holdout observed long "
            f"enough; median {play['median_days_observed']:.0f} days observed).",
            f"- Result: {play['verdict']}",
        ]
        if "srm" in play:
            srm = play["srm"]
            state = "as designed" if srm["ok"] else "NOT as designed"
            lines.append(
                f"- Split check: {srm['observed_holdout_share']:.0%} in holdout against "
                f"{srm['expected_holdout_share']:.0%} planned: {state} (p = {srm['p_value']:.2f})."
            )
            guard = play["guardrail_retention"]
            lines.append(
                f"- Guardrail, still a customer: {guard['rate_treatment']:.0%} treatment, "
                f"{guard['rate_holdout']:.0%} holdout."
            )
        treated, held = play["money"]["treatment"], play["money"]["holdout"]
        if treated["arr_at_entry"] and held["arr_at_entry"]:
            lines.append(
                f"- Revenue retained: {treated['retained_arr_share']:.1%} of "
                f"${treated['arr_at_entry']:,.0f} (treatment), {held['retained_arr_share']:.1%} of "
                f"${held['arr_at_entry']:,.0f} (holdout)."
            )
            lines.append(
                f"- Expansion won in the window: ${treated['expansion_won']:,.0f} treatment "
                f"(${treated['expansion_per_account']:,.0f} per account), "
                f"${held['expansion_won']:,.0f} holdout "
                f"(${held['expansion_per_account']:,.0f} per account)."
            )
        if play["ladder"]:
            lines += ["", "By highest rung of the ladder reached (treatment):", "",
                      "| Rung | Accounts | Reached the goal | Rate |", "|---|---|---|---|"]  # fmt: skip
            lines += [
                f"| {row['tier']} | {row['accounts']} | {row['successes']} | {row['rate']:.0%} |"
                for row in play["ladder"]
            ]
        if play["cohorts"]:
            lines += ["", "By week of entry:", "",
                      "| Week starting | Treatment | Holdout |", "|---|---|---|"]  # fmt: skip
            for row in play["cohorts"]:
                lines.append(
                    f"| {row['week_starting']} | {_cohort(row, 'treatment')} | "
                    f"{_cohort(row, 'holdout')} |"
                )

    handoffs = results["handoffs"]
    lines += [
        "",
        "## Human fallback",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Handoffs to people | {handoffs['handoffs']} ({handoffs['open_now']} open now) |",
        f"| SLA breach rate | {_pct(handoffs['sla_breach_rate'])} |",
        f"| Escalation conversion (closed with a good outcome) | "
        f"{_pct(handoffs['escalation_conversion'])} |",
        f'| Unnecessary handoffs ("the agent should have handled this") | '
        f"{_pct(handoffs['unnecessary_handoff_rate'])} |",
        f"| Handoffs from the agent | {handoffs['agent_handoffs']} |",
        f"| Docs gap (agent handoffs because no article covered the question) | "
        f"{_pct(handoffs['docs_gap_share'])} |",
        "",
        "## How to read this",
        "",
        "- **Lift** is the treatment rate minus the holdout rate, in percentage points.",
        "- **The interval** is where the true lift plausibly lies. If it includes zero, the",
        "  play may have done nothing.",
        "- **p** is how often a gap this large would appear if the play did nothing. Below",
        '  0.05 is the bar for "working".',
        "- **Split check**: assignment is by hash, so the holdout share should match the",
        "  design. If it does not, something is filtering one group and the comparison is void.",
        "- **By rung**: accounts that needed a person are the harder cases. A lower rate on",
        "  the human rung does not mean people perform worse.",
        "- Thirty days cannot show churn. Plays are judged on leading indicators (setup",
        "  finished, usage recovered); retention is watched as a guardrail.",
        "",
    ]
    return "\n".join(lines)


def _rate(play: dict, arm: str) -> str:
    n = play[f"n_{arm}"]
    if not n:
        return "none"
    return f"{play[f'successes_{arm}'] / n:.0%} ({play[f'successes_{arm}']}/{n})"


def _lift(play: dict) -> str:
    if "lift" not in play:
        return "n/a"
    return f"{play['lift']:+.0%} ({play['ci_low']:+.0%} to {play['ci_high']:+.0%})"


def _p(play: dict) -> str:
    return f"{play['p_value']:.3f}" if "p_value" in play else "n/a"


def _cohort(row: dict, arm: str) -> str:
    if not row[f"n_{arm}"]:
        return "none"
    return f"{row[f'rate_{arm}']:.0%} of {row[f'n_{arm}']}"


def _share(part, whole) -> float | None:
    return float(part) / float(whole) if whole else None


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0%}"
