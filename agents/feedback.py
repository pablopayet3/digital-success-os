"""Classify what customers wrote: NPS comments and high-priority ticket texts.

Synthetic data, fictional company.

A score says how unhappy a customer is. The comment says why. A small model reads
each recent comment once and stores its sentiment and theme (setup, usability,
performance, support, pricing, value). The themes feed the "voice of the customer"
view in the app, and they tell a play owner what the detractors are unhappy about.

Cost control: only the last 30 days, at most MAX_TEXTS_PER_DAY texts a day, eight
texts per call, and each text is classified once.
"""

from __future__ import annotations

from agents.classify import classify_feedback
from common.warehouse import open_warehouse
from engine.context import DayContext, records

MAX_TEXTS_PER_DAY = 80


def classify_new_feedback(ctx: DayContext, limit: int = MAX_TEXTS_PER_DAY) -> int:
    """Classify recent texts not yet classified. Returns how many were classified."""
    done = {row["text_id"] for row in ctx.store.rows("SELECT text_id FROM text_classifications")}
    since = ctx.days_ago(30)
    warehouse = open_warehouse(ctx.data_dir)
    texts = records(
        warehouse.query(
            f"""
            SELECT response_id AS text_id, 'nps_comment' AS kind, account_id, comment AS body
            FROM silver.stg_nps
            WHERE comment IS NOT NULL AND comment <> '' AND responded_date >= DATE '{since}'
            UNION ALL
            SELECT ticket_id, 'ticket', account_id, subject || '. ' || body
            FROM silver.stg_tickets
            WHERE is_high_priority AND created_date >= DATE '{since}'
            ORDER BY text_id
            """
        )
    )
    warehouse.close()
    new = [text for text in texts if text["text_id"] not in done][:limit]
    if not new:
        return 0

    results = classify_feedback([{"id": t["text_id"], "text": t["body"]} for t in new])
    rows = [
        {
            "text_id": text["text_id"],
            "kind": text["kind"],
            "account_id": text["account_id"],
            "sentiment": results[text["text_id"]]["sentiment"],
            "theme": results[text["text_id"]]["theme"],
            "confidence": results[text["text_id"]]["confidence"],
            "classified_on": ctx.day,
        }
        for text in new
        if text["text_id"] in results  # unclassified texts are tried again tomorrow
    ]
    if rows:
        ctx.store.insert("text_classifications", *rows)
    return len(rows)
