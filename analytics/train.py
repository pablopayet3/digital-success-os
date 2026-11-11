"""Train the churn-risk and expansion-propensity models.

Synthetic data, fictional company.

Run with:  uv run python run.py train

How it works, for each of the two models:
  1. Take snapshots of the gold table on past days. Each row is an account on a day.
  2. Attach the label: did the account churn (or expand) in the following 90 days?
     Labels come from the CRM, and only snapshots whose 90 days have passed are used.
  3. Split by time: train on earlier snapshots, test on the latest one.
  4. Fit a logistic regression (explainable) and a gradient-boosting model (benchmark).
  5. Pick the score threshold from team capacity: how many accounts can people act on?
  6. Save the model, its metrics and a model card.

Logistic regression is the production model: a CSM can be told why an account is
flagged. Gradient boosting is reported next to it so we know what we give up.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import duckdb
import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from analytics.features import FEATURES, SOURCE_TABLE, build_features
from analytics.model_card import CARD_DIR, write_model_card
from common.config import load_yaml
from common.paths import DATA_DIR, ROOT
from ingest.load import warehouse_path

MODEL_DIR = ROOT / "analytics" / "models"
CLUSTER_FEATURES = [
    "active_seat_share", "active_days_per_seat", "seat_utilisation", "setup_closure",
    "tickets_30d", "email_open_rate",
]  # fmt: skip


def train_all(
    data_dir: Path = DATA_DIR,
    model_dir: Path = MODEL_DIR,
    card_dir: Path = CARD_DIR,
    verbose: bool = True,
) -> dict:
    """Train both models and the behaviour clusters. Returns the metrics of each model."""
    cfg = load_yaml("models.yaml")
    model_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(warehouse_path(data_dir)))
    test_day, train_days = pick_snapshot_days(con, cfg)
    rows = load_snapshots(con, [*train_days, test_day])
    today_rows = con.execute(
        f"""
        SELECT * FROM {SOURCE_TABLE}
        WHERE snapshot_date = (SELECT max(snapshot_date) FROM {SOURCE_TABLE})
        """
    ).df()
    con.close()

    results = {}
    for name in ("churn", "expansion"):
        results[name] = train_one(name, rows, train_days, test_day, cfg, model_dir)
        write_model_card(name, results[name], card_dir)
        if verbose:
            print_metrics(name, results[name])
    train_clusters(today_rows, cfg, model_dir)
    return results


def pick_snapshot_days(con, cfg: dict) -> tuple[date, list[date]]:
    """The test day is the latest day whose outcome is fully observed."""
    first_day, test_day = con.execute(
        """
        SELECT min(snapshot_date), max(snapshot_date) FILTER (WHERE outcome_observed)
        FROM gold.fct_outcome_labels
        """
    ).fetchone()
    if test_day is None:
        raise ValueError("History is too short: no day has a fully observed 90-day outcome.")
    train_days = [test_day - timedelta(days=n) for n in cfg["train_days_before_test"]]
    train_days = [day for day in train_days if day >= first_day + timedelta(days=14)]
    if not train_days:
        raise ValueError("History is too short: no training snapshot before the test day.")
    return test_day, sorted(train_days)


def load_snapshots(con, days: list[date]) -> pd.DataFrame:
    """Gold rows for the chosen days, with their outcome labels."""
    day_list = ", ".join(f"DATE '{day}'" for day in days)
    return con.execute(
        f"""
        SELECT facts.*, labels.churned_within_90d, labels.expanded_within_90d
        FROM {SOURCE_TABLE} AS facts
        INNER JOIN gold.fct_outcome_labels AS labels
            ON facts.account_id = labels.account_id
            AND facts.snapshot_date = labels.snapshot_date
        WHERE facts.snapshot_date IN ({day_list})
        """
    ).df()


def train_one(
    name: str,
    rows: pd.DataFrame,
    train_days: list[date],
    test_day: date,
    cfg: dict,
    model_dir: Path,
) -> dict:
    label = cfg[name]["label"]
    snapshot = pd.to_datetime(rows["snapshot_date"]).dt.date
    train, test = rows[snapshot.isin(train_days)], rows[snapshot == test_day]
    x_train, y_train = build_features(train), train[label].astype(int)
    x_test, y_test = build_features(test), test[label].astype(int)

    logistic = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=0.5))
    logistic.fit(x_train, y_train)
    boosting = HistGradientBoostingClassifier(
        max_depth=3, learning_rate=0.05, max_iter=150, random_state=cfg["random_state"]
    )
    boosting.fit(x_train, y_train)

    scores = logistic.predict_proba(x_test)[:, 1]
    benchmark_scores = boosting.predict_proba(x_test)[:, 1]

    # Threshold by capacity: rank the pilot segment by score and draw the line where
    # the team runs out of hands. Everything at or above that score gets flagged.
    capacity = cfg[name]["capacity_accounts"]
    pilot = (test["coverage_tier"] == "uncovered").to_numpy()
    pilot_scores = np.sort(scores[pilot])[::-1]
    threshold = float(pilot_scores[min(capacity, len(pilot_scores)) - 1])
    flagged = pilot & (scores >= threshold)

    coefficients = logistic[-1].coef_[0]
    order = np.argsort(-np.abs(coefficients))
    result = {
        "model": name,
        "label": label,
        "production_model": "logistic regression (standardised features)",
        "benchmark_model": "gradient boosting (depth 3)",
        "train_days": [str(day) for day in train_days],
        "test_day": str(test_day),
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "train_positive_rate": round(float(y_train.mean()), 4),
        "test_positive_rate": round(float(y_test.mean()), 4),
        "logistic": evaluate(y_test.to_numpy(), scores),
        "boosting": evaluate(y_test.to_numpy(), benchmark_scores),
        "calibration": calibration_table(y_test.to_numpy(), scores),
        "capacity_accounts": capacity,
        "threshold": round(threshold, 4),
        "flagged_in_pilot_segment": int(flagged.sum()),
        "precision_at_threshold": round(float(y_test.to_numpy()[flagged].mean()), 4),
        "recall_at_threshold": round(
            float(y_test.to_numpy()[flagged].sum() / max(1, y_test.to_numpy()[pilot].sum())), 4
        ),
        "pilot_segment_base_rate": round(float(y_test.to_numpy()[pilot].mean()), 4),
        "top_drivers": [
            {"feature": FEATURES[i], "coefficient": round(float(coefficients[i]), 3)}
            for i in order[:8]
        ],
    }
    joblib.dump(logistic, model_dir / f"{name}_model.joblib")
    (model_dir / f"{name}_metrics.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def evaluate(actual: np.ndarray, scores: np.ndarray) -> dict:
    """The three numbers that matter: ranking, what the team would see, and honesty."""
    top = max(1, round(0.10 * len(scores)))
    top_rows = np.argsort(-scores)[:top]
    return {
        "auc": round(float(roc_auc_score(actual, scores)), 4),
        # of the 10% of accounts the model ranks highest, how many really had the outcome?
        "precision_at_top_10pct": round(float(actual[top_rows].mean()), 4),
        "recall_at_top_10pct": round(float(actual[top_rows].sum() / max(1, actual.sum())), 4),
        # Brier score: average squared gap between predicted chance and what happened
        "brier": round(float(brier_score_loss(actual, scores)), 4),
    }


def calibration_table(actual: np.ndarray, scores: np.ndarray, bins: int = 5) -> list[dict]:
    """Split accounts into five equal groups by score: predicted chance vs what happened."""
    frame = pd.DataFrame({"score": scores, "actual": actual})
    frame["group"] = pd.qcut(frame["score"].rank(method="first"), bins, labels=False)
    table = frame.groupby("group").agg(
        accounts=("actual", "size"), predicted=("score", "mean"), observed=("actual", "mean")
    )
    return [
        {
            "group": int(group) + 1,
            "accounts": int(row["accounts"]),
            "predicted": round(float(row["predicted"]), 3),
            "observed": round(float(row["observed"]), 3),
        }
        for group, row in table.iterrows()
    ]


def train_clusters(today_rows: pd.DataFrame, cfg: dict, model_dir: Path) -> None:
    """Group today's accounts by behaviour (k-means) and give each group a plain name."""
    features = build_features(today_rows)[CLUSTER_FEATURES]
    model = make_pipeline(
        StandardScaler(),
        KMeans(n_clusters=cfg["clusters"], n_init=10, random_state=cfg["random_state"]),
    )
    labels = model.fit_predict(features)
    centres = features.groupby(labels).mean()
    joblib.dump({"model": model, "names": name_clusters(centres)}, model_dir / "clusters.joblib")


def name_clusters(centres: pd.DataFrame) -> dict[int, str]:
    """Name each cluster after what stands out about its average account."""
    names: dict[int, str] = {}
    remaining = list(centres.index)

    def take(column: str, highest: bool, name: str) -> None:
        if remaining:
            ranked = centres.loc[remaining, column]
            chosen = ranked.idxmax() if highest else ranked.idxmin()
            names[int(chosen)] = name
            remaining.remove(chosen)

    take("active_seat_share", False, "Dormant seats")
    take("tickets_30d", True, "Needs help")
    take("active_days_per_seat", True, "Power users")
    for leftover in list(remaining):
        names[int(leftover)] = "Steady adopters" if len(names) == 3 else f"Group {leftover}"
    return names


def print_metrics(name: str, result: dict) -> None:
    print(
        f"\n{name} model  (test day {result['test_day']}, {result['test_rows']} accounts, "
        f"{result['test_positive_rate']:.1%} positive)"
    )
    for label, key in (("logistic regression", "logistic"), ("gradient boosting  ", "boosting")):
        scores = result[key]
        print(
            f"  {label}: AUC {scores['auc']:.3f}, "
            f"precision in top 10% {scores['precision_at_top_10pct']:.1%}, "
            f"Brier {scores['brier']:.3f}"
        )
    print(
        f"  capacity {result['capacity_accounts']} accounts -> cut-off {result['threshold']:.3f}: "
        f"precision {result['precision_at_threshold']:.1%}, "
        f"recall {result['recall_at_threshold']:.1%}, "
        f"base rate {result['pilot_segment_base_rate']:.1%}"
    )
    drivers = [f"{d['feature']} ({d['coefficient']:+.2f})" for d in result["top_drivers"][:5]]
    print("  strongest drivers: " + ", ".join(drivers))


if __name__ == "__main__":
    train_all()
