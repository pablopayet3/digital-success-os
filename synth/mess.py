"""Deliberate data problems, so the data-quality checks have something to catch.

Synthetic data, fictional company. The world itself stays clean; the mess is
added only when files are written. Everything injected is recorded in an
"issue log" (saved as data/ground_truth/injected_issues.json), so Phase 2 can
prove that the pipeline caught exactly these rows.
"""

from __future__ import annotations

import json

from synth.util import pick, stable_uniform

UNKNOWN_EVENT_NAMES = ["userActive", "board_archived_v2", "test_event", "page_view", "legacy_sync"]

# The same persona written the way people really type it into a CRM.
PERSONA_VARIANTS = {
    "admin": ["Admin", "ADMIN ", "administrator", "Workspace admin"],
    "billing": ["Billing", "billing contact", "Finance"],
    "champion": ["Champion", "champ", "CHAMPION"],
    "end_user": ["End User", "end-user", "user", "EndUser"],
}


def new_issue_log() -> dict:
    return {
        "missing_account_id": [],  # event ids
        "future_timestamp": [],  # event ids
        "unknown_event_name": [],  # event ids
        "duplicate_event_id": [],  # event ids that appear twice
        "malformed_lines": 0,  # lines that are not valid JSON
        "late_arriving": {},  # filled in by generate.py
        "duplicate_contact_email": [],  # contact ids of the extra rows
        "messy_persona": 0,  # contact rows with a non-standard persona spelling
    }


def to_line(event: dict) -> str:
    return json.dumps(event, separators=(",", ":"))


def messy_event_lines(events: list[dict], rng, rates: dict, issues: dict) -> list[str]:
    """Turn a day of events into JSON lines, damaging a small share of them.

    Each event gets at most one problem, so the counts in the issue log add up exactly.
    """
    cut_missing = rates["missing_account_id_rate"]
    cut_future = cut_missing + rates["future_timestamp_rate"]
    cut_unknown = cut_future + rates["unknown_event_name_rate"]
    cut_duplicate = cut_unknown + rates["duplicate_event_rate"]
    cut_malformed = cut_duplicate + rates["malformed_line_rate"]

    lines, duplicates = [], []
    rolls = rng.random(len(events)).tolist()
    for event, roll in zip(events, rolls, strict=True):
        if roll >= cut_malformed:
            lines.append(to_line(event))  # the normal case: untouched
        elif roll < cut_missing:
            lines.append(to_line({**event, "account_id": None}))
            issues["missing_account_id"].append(event["event_id"])
        elif roll < cut_future:
            # A device with a wrong clock: the event claims to be from two years ahead.
            stamp = event["occurred_at"]
            wrong_time = str(int(stamp[:4]) + 2) + stamp[4:]
            lines.append(to_line({**event, "occurred_at": wrong_time}))
            issues["future_timestamp"].append(event["event_id"])
        elif roll < cut_unknown:
            lines.append(to_line({**event, "event_name": pick(rng, UNKNOWN_EVENT_NAMES)}))
            issues["unknown_event_name"].append(event["event_id"])
        elif roll < cut_duplicate:
            lines.append(to_line(event))
            duplicates.append(to_line(event))  # the same event delivered a second time
            issues["duplicate_event_id"].append(event["event_id"])
        else:
            line = to_line(event)
            lines.append(line[: len(line) // 2])  # cut off mid-way: not valid JSON
            issues["malformed_lines"] += 1
    return lines + duplicates


def messy_contact_rows(rows: list[dict], rates: dict, issues: dict) -> list[dict]:
    """Add duplicate contacts and inconsistent persona spellings to the CRM export.

    The choice is tied to the contact id, not to a random draw, so the same
    contacts are affected every time the file is written.
    """
    out = []
    for row in rows:
        row = dict(row)
        contact_id = row["contact_id"]
        if stable_uniform(contact_id, "persona") < rates["messy_persona_rate"]:
            variants = PERSONA_VARIANTS[row["persona"]]
            row["persona"] = variants[int(stable_uniform(contact_id, "variant") * len(variants))]
            issues["messy_persona"] += 1
        out.append(row)
        if stable_uniform(contact_id, "duplicate") < rates["duplicate_contact_email_rate"]:
            # The same person entered twice, with the email typed in capitals.
            copy = {**row, "contact_id": contact_id + "-DUP", "email": row["email"].upper()}
            out.append(copy)
            issues["duplicate_contact_email"].append(copy["contact_id"])
    return out
