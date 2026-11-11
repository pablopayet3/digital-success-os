"""Score every account with the trained models and write the scores to the warehouse.

Synthetic data, fictional company.

Runs inside the pipeline, between the two dbt stages:
    dbt (facts and health)  ->  this file (scores)  ->  dbt (lifecycle and signals)

Writes two tables:
    gold.account_scores    churn-risk and expansion scores per account per day,
                           a flag for the accounts the team has capacity to act on,
                           and the top reasons in plain words
    gold.account_clusters  the behaviour cluster of each account today

If the models have not been trained yet, the tables are still written (with empty
scores), so the rest of the pipeline keeps working.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import joblib
import numpy as np
import pandas as pd

from analytics.features import FEATURE_PHRASES, FEATURES, SOURCE_TABLE, build_features
from analytics.train import CLUSTER_FEATURES, MODEL_DIR
from common.config import load_yaml
from common.paths import DATA_DIR
from ingest.load import warehouse_path

# model name -> (score column, flag column, reasons column)
OUTPUT_COLUMNS = {
    "churn": ("churn_risk_score", "churn_risk_high", "churn_top_reasons"),
    "expansion": ("expansion_score", "expansion_ready", "expansion_top_reasons"),
}
# In the model, but never shown as a reason for a score.
NOT_A_REASON = ["has_assist", "has_docs", "seats_licensed_log", "account_age_log"]


def score_accounts(data_dir: Path = DATA_DIR, model_dir: Path = MODEL_DIR) -> int:
    """Score all account-days. Returns the number of rows scored."""
    con = duckdb.connect(str(warehouse_path(data_dir)))
    rows = con.execute(f"SELECT * FROM {SOURCE_TABLE}").df()
    features = build_features(rows)
    scores = rows[["account_id", "snapshot_date"]].copy()

    capacity = load_yaml("models.yaml")
    in_pilot = rows["coverage_tier"] == "uncovered"
    for name, (score_column, flag_column, reasons_column) in OUTPUT_COLUMNS.items():
        model_path = model_dir / f"{name}_model.joblib"
        if model_path.exists():
            model = joblib.load(model_path)
            scores[score_column] = model.predict_proba(features)[:, 1].round(4)
            scores[flag_column] = flag_by_capacity(
                scores, score_column, in_pilot, capacity[name]["capacity_accounts"]
            )
            scores[reasons_column] = top_reasons(model, features)
        else:
            scores[score_column], scores[flag_column], scores[reasons_column] = np.nan, False, None

    con.execute(
        """
        CREATE OR REPLACE TABLE gold.account_scores AS
        SELECT
            account_id,
            CAST(snapshot_date AS DATE) AS snapshot_date,
            CAST(churn_risk_score AS DOUBLE) AS churn_risk_score,
            CAST(churn_risk_high AS BOOLEAN) AS churn_risk_high,
            CAST(churn_top_reasons AS VARCHAR) AS churn_top_reasons,
            CAST(expansion_score AS DOUBLE) AS expansion_score,
            CAST(expansion_ready AS BOOLEAN) AS expansion_ready,
            CAST(expansion_top_reasons AS VARCHAR) AS expansion_top_reasons
        FROM scores
        """
    )

    today = rows[rows["snapshot_date"] == rows["snapshot_date"].max()]
    clusters = today[["account_id"]].copy()
    cluster_path = model_dir / "clusters.joblib"
    if cluster_path.exists():
        saved = joblib.load(cluster_path)
        labels = saved["model"].predict(build_features(today)[CLUSTER_FEATURES])
        clusters["cluster_name"] = [saved["names"][int(label)] for label in labels]
    else:
        clusters["cluster_name"] = None
    con.execute(
        """
        CREATE OR REPLACE TABLE gold.account_clusters AS
        SELECT account_id, CAST(cluster_name AS VARCHAR) AS cluster_name FROM clusters
        """
    )
    con.close()
    return len(scores)


def flag_by_capacity(
    scores: pd.DataFrame, score_column: str, in_pilot: pd.Series, capacity: int
) -> pd.Series:
    """Flag the accounts people have the capacity to act on.

    Each day, the cut-off is the score of the Nth highest-scoring account in the
    pilot segment, where N is the team's capacity. Every account at or above that
    score is flagged. The cut-off moves with the customer base, so the queue never
    outgrows the team (docs/decisions/0004-churn-threshold-by-capacity.md).
    """
    cut_off_by_day = (
        scores[in_pilot]
        .groupby("snapshot_date")[score_column]
        .apply(lambda day_scores: day_scores.nlargest(capacity).min())
    )
    return scores[score_column] >= scores["snapshot_date"].map(cut_off_by_day)


def top_reasons(model, features: pd.DataFrame, how_many: int = 3) -> list[str]:
    """Explain each score: the features that push it up the most, in plain words.

    Works because the model is a logistic regression on standardised features: each
    feature's push is its coefficient times how far the account is from average.
    Fixed descriptions of the account (size, age, products owned) stay in the model
    but are not offered as reasons: a CSM cannot act on them.
    """
    scaler, logistic = model[0], model[-1]
    distance_from_average = scaler.transform(features)
    push = distance_from_average * logistic.coef_[0]
    push[:, [FEATURES.index(name) for name in NOT_A_REASON]] = 0.0
    strongest = np.argsort(-push, axis=1)[:, :how_many]

    reasons = []
    for row, columns in enumerate(strongest):
        phrases = []
        for column in columns:
            if push[row, column] <= 0.05:
                continue  # this feature does not push the score up
            high_phrase, low_phrase = FEATURE_PHRASES[FEATURES[column]]
            phrases.append(high_phrase if distance_from_average[row, column] > 0 else low_phrase)
        reasons.append(", ".join(phrases) if phrases else "no single strong driver")
    return reasons
