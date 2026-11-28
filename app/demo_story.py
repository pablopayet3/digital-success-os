"""The Live demo's scripted story and its list of customers, shared by the page and by
scripts/story_answers.py, which stores the model's answers so the story replays at once.

Synthetic data, fictional company.
"""

from __future__ import annotations

import pandas as pd

from app import ui

# The two messages of the demo path: a setup question the agent answers, then a message
# with two needs, a price (Sales, in Salesforce) and a person to help with single sign-on
# (the Customer Success team, in Gainsight). Each need gets one owner.
STORY = [
    "How do I invite my whole team at once?",
    "Thanks. How much would 10 more seats cost? And could someone help us set up single sign-on?",
]


def stalled_customers() -> pd.DataFrame:
    """The customers the page lists: those whose "setup stalled" signal fires today first."""
    return ui.query(
        """
        SELECT account_id, account_name, edition, prerequisite_closure_pct
        FROM gold.account_current
        WHERE coverage_tier = 'uncovered' AND prerequisite_closure_pct < 1 AND contacts_total > 0
        ORDER BY CASE WHEN signals_firing LIKE '%activation_stalled%' THEN 0 ELSE 1 END, account_id
        LIMIT 25
        """
    )


def first_customer(ids: list[str]) -> int:
    """Where the page opens: the first customer who really received the play's first email."""
    emails = ui.rows("SELECT DISTINCT account_id FROM touches WHERE channel = 'email'")
    emailed = set(emails["account_id"]) if len(emails) else set()
    return next((position for position, one in enumerate(ids) if one in emailed), 0)


def demo_accounts() -> list[str]:
    """The customers in the order a presenter meets them: the one the page opens on first."""
    ids = list(stalled_customers()["account_id"])
    if not ids:
        return []
    start = first_customer(ids)
    return [ids[start]] + ids[:start] + ids[start + 1 :]
