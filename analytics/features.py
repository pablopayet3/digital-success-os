"""Turn rows of the gold table into model features.

Synthetic data, fictional company. Every feature is built only from columns of
gold.int_account_daily_health as they stood on the snapshot day. Nothing from
data/ground_truth/ is ever used here.

Each feature has two short phrases, one for a high value and one for a low
value. They are used to explain a score in plain words ("few seats active").
"""

from __future__ import annotations

import numpy as np
import pandas as pd

SOURCE_TABLE = "gold.int_account_daily_health"

# feature name -> (what a high value means, what a low value means)
FEATURE_PHRASES = {
    "active_seat_share": ("most seats active", "few seats active"),
    "mau_change": ("usage growing", "usage falling"),
    "active_days_per_seat": ("used most days", "rarely used"),
    "admin_logins_30d": ("admin logs in often", "admin rarely logs in"),
    "setup_closure": ("setup complete", "setup incomplete"),
    "seat_utilisation": ("nearly all seats assigned", "many seats unassigned"),
    "seat_growth_30d": ("seats growing", "seats flat or shrinking"),
    "tickets_30d": ("many support tickets", "few support tickets"),
    "high_priority_tickets_30d": ("many high-priority tickets", "no high-priority tickets"),
    "open_high_priority_tickets": ("high-priority tickets still open", "no open escalations"),
    "nps_score": ("high NPS", "low NPS"),
    "nps_missing": ("never answered NPS", "has answered NPS"),
    "email_open_rate": ("reads our emails", "ignores our emails"),
    "account_age_log": ("long-standing account", "new account"),
    "renewal_within_60d": ("renewal within 60 days", "renewal not close"),
    "seats_licensed_log": ("large account", "small account"),
    "rules_vs_limit": ("near the automation limit", "few automation rules"),
    "integrations_vs_limit": ("near the integration limit", "few integrations"),
    "assist_credits_vs_included": ("heavy Assist use", "little Assist use"),
    "boards_per_seat_30d": ("creating many boards", "creating few boards"),
    "is_free": ("free edition", "paid edition"),
    "has_docs": ("owns Docs", "no Docs"),
    "has_assist": ("owns Assist", "no Assist"),
}
FEATURES = list(FEATURE_PHRASES)


def build_features(rows: pd.DataFrame) -> pd.DataFrame:
    """One row of features per row of the gold table."""
    seats = rows["seats_assigned"].clip(lower=1)
    features = pd.DataFrame(index=rows.index)

    # Usage
    features["active_seat_share"] = (rows["mau_30d"] / seats).clip(upper=1)
    prior = rows["mau_prior_30d"].where(rows["mau_prior_30d"] > 0)
    features["mau_change"] = (rows["mau_30d"] / prior).clip(upper=3).fillna(1.0)
    features["active_days_per_seat"] = rows["active_user_days_30d"] / seats
    features["admin_logins_30d"] = rows["admin_logins_30d"]
    features["setup_closure"] = rows["prerequisite_closure_pct"]
    features["boards_per_seat_30d"] = rows["boards_created_30d"] / seats

    # Seats
    features["seat_utilisation"] = rows["seat_utilisation"]
    seats_before = rows["seats_assigned_30d_ago"]
    growth = (rows["seats_assigned"] - seats_before) / seats_before.clip(lower=1)
    features["seat_growth_30d"] = growth.fillna(0.0)
    features["seats_licensed_log"] = np.log1p(rows["seats_licensed"])

    # Support and sentiment
    features["tickets_30d"] = rows["tickets_30d"]
    features["high_priority_tickets_30d"] = rows["high_priority_tickets_30d"]
    features["open_high_priority_tickets"] = rows["open_high_priority_tickets"]
    features["nps_score"] = rows["latest_nps_score"].fillna(7)
    features["nps_missing"] = rows["latest_nps_score"].isna().astype(int)
    sent = rows["emails_sent_30d"].where(rows["emails_sent_30d"] > 0)
    features["email_open_rate"] = (rows["emails_opened_30d"] / sent).fillna(0.3)

    # Lifecycle and commercial
    features["account_age_log"] = np.log1p(rows["account_age_days"])
    features["renewal_within_60d"] = (rows["days_to_renewal"] <= 60).astype(int)

    # Edition limits and products
    features["rules_vs_limit"] = (
        rows["automation_rules_total"] / rows["automation_rule_limit"]
    ).clip(upper=1)
    features["integrations_vs_limit"] = (
        rows["integrations_total"] / rows["integration_limit"]
    ).clip(upper=1)
    included = rows["assist_credits_included"].where(rows["assist_credits_included"] > 0)
    features["assist_credits_vs_included"] = (
        (rows["assist_credits_30d"] / included).clip(upper=2).fillna(0.0)
    )
    features["is_free"] = (rows["edition"] == "free").astype(int)
    features["has_docs"] = rows["has_docs"].astype(int)
    features["has_assist"] = rows["has_assist"].astype(int)

    return features[FEATURES].astype(float)
