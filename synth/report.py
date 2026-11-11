"""A plain-text summary of the generated world.

Synthetic data, fictional company. The report answers one practical question
before any pipeline exists: does each play have enough accounts to test? The
signal counts are quick approximations taken straight from the simulator; the
real signals are built in SQL in Phase 3.
"""

from __future__ import annotations

from collections import Counter
from datetime import timedelta

from synth.behavior import assist_credits_30d, at_edition_limit, seat_utilisation, setup_closure


def signal_preview(world) -> dict[str, int]:
    """How many active, uncovered accounts would qualify for each signal today."""
    today = world.last_day
    accounts = [
        a
        for a in world.accounts
        if a.status == "active" and a.contract_start <= today and a.coverage_tier == "uncovered"
    ]
    ids = {a.account_id for a in accounts}

    recent_detractors = {
        r["account_id"]
        for r in world.nps
        if r["score"] <= 6 and r["responded_at"].date() > today - timedelta(days=14)
    }
    month_ago = today - timedelta(days=30)
    serious_tickets = Counter(
        t["account_id"]
        for t in world.tickets
        if t["priority"] in ("high", "urgent") and t["created_at"].date() > month_ago
    )

    def usage_dropped(a) -> bool:
        last, before = sum(a.dau_log[-30:]), sum(a.dau_log[-60:-30])
        return len(a.dau_log) >= 60 and before > 0 and last <= 0.7 * before

    def has_valid_admin(a) -> bool:
        return any(
            c.persona == "admin" and c.consent_status == "opted_in" and c.email_valid
            for c in a.contacts
        )

    def doc_like_boards(a) -> int:
        return sum(1 for day in a.doc_like_board_days if day > world.day_index - 60)

    return {
        "accounts in pilot segment (uncovered, active)": len(accounts),
        "activation_stalled": sum(
            1 for a in accounts if (today - a.contract_start).days >= 7 and setup_closure(a) < 0.5
        ),
        "usage_drop (approx.)": sum(1 for a in accounts if usage_dropped(a)),
        "seat_pressure": sum(1 for a in accounts if seat_utilisation(a) >= 0.9),
        "edition_fit": sum(
            1 for a in accounts if a.edition != "enterprise" and at_edition_limit(world, a)
        ),
        "cross_product": sum(
            1 for a in accounts if "docs" not in a.products and doc_like_boards(a) >= 3
        ),
        "detractor": len(recent_detractors & ids),
        "support_friction": sum(1 for a, n in serious_tickets.items() if n >= 3 and a in ids),
        "no_valid_admin": sum(1 for a in accounts if not has_valid_admin(a)),
    }


def label_preview(world) -> list[str]:
    """Check that 90-day outcomes are observable inside the history window."""
    lines = []
    history_days = world.day_index
    for snapshot_day in (60, 90):
        if snapshot_day + 90 > history_days:
            continue
        snapshot = world.start_date + timedelta(days=snapshot_day)
        window_end = snapshot + timedelta(days=90)
        at_risk = [
            a
            for a in world.accounts
            if a.contract_start <= snapshot and (a.churned_at is None or a.churned_at > snapshot)
        ]
        churned = sum(1 for a in at_risk if a.churned_at and a.churned_at <= window_end)
        expanded_ids = {
            o["account_id"]
            for o in world.opportunities
            if o["type"] == "expansion" and snapshot < o["close_date"] <= window_end
        }
        expanded = sum(1 for a in at_risk if a.account_id in expanded_ids)
        lines.append(
            f"- snapshot on day {snapshot_day}: {len(at_risk)} accounts, "
            f"{churned} churned within 90 days ({churned / len(at_risk):.1%}), "
            f"{expanded} expanded within 90 days ({expanded / len(at_risk):.1%})"
        )
    return lines


def build_report(world, row_counts: dict[str, int], issues: dict) -> str:
    today = world.last_day
    live = [a for a in world.accounts if a.contract_start <= today]
    active = [a for a in live if a.status == "active"]
    consumption = sum(assist_credits_30d(a) for a in active)

    lines = [
        "# Generation report",
        "",
        "Synthetic data, fictional company (Lumen Labs / Relay).",
        "",
        f"- Simulated days: {world.day_index} ({world.start_date} to {today})",
        f"- Accounts signed up so far: {len(live)} "
        f"({len(active)} active, {len(live) - len(active)} churned)",
        f"- Accounts that sign up later (during the pilot): {len(world.accounts) - len(live)}",
        f"- Assist credits used in the last 30 days: {consumption}",
        "",
        "## Rows per source",
        "",
    ]
    lines += [f"- {name}: {count:,}" for name, count in row_counts.items()]

    lines += ["", "## Accounts by coverage tier, segment and edition", ""]
    for field in ("coverage_tier", "segment", "edition"):
        counts = Counter(getattr(a, field) for a in live)
        lines.append(f"- {field}: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))

    lines += ["", "## Accounts that would qualify for each signal today (pilot segment)", ""]
    lines += [f"- {name}: {count}" for name, count in signal_preview(world).items()]

    lines += ["", "## Outcomes observable in history (labels for the Phase 3 models)", ""]
    lines += label_preview(world) or ["- history is too short for a 90-day outcome window"]

    lines += ["", "## Data problems injected on purpose", ""]
    for name, value in issues.items():
        if isinstance(value, list):
            lines.append(f"- {name}: {len(value)}")
        elif isinstance(value, dict):
            lines.append(f"- {name}: " + ", ".join(f"{k}={v}" for k, v in value.items()))
        else:
            lines.append(f"- {name}: {value}")
    return "\n".join(lines) + "\n"
