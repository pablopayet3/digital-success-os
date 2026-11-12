"""A person's verdict on a conversation the agent had: the feedback loop.

Synthetic data, fictional company. Two ways a conversation reaches the review queue
(the `eval_candidates` table):

  1. A person closes a handoff as "the agent should have handled this"
     (engine/handoff.py).
  2. A person reading a conversation gives it a thumbs down (this file).

Either way the conversation becomes a draft evaluation case. A person turns the draft
into a proper case with an expected behaviour, and the next prompt version has to pass
it. Nothing here changes how the agent behaves today.
"""

from __future__ import annotations

import json
from pathlib import Path

from common.store import Store
from engine.handoff import FEEDBACK_DIR

THUMBS_DOWN = "thumbs down on a conversation"


def rate_conversation(
    store: Store,
    conversation_id: str,
    handled_well: bool,
    notes: str,
    day: str,
    export_to: Path | None = FEEDBACK_DIR,
) -> None:
    """Record a thumbs up or down. A thumbs down also queues the conversation for review.

    Safe to repeat: rating the same conversation again replaces the earlier rating.
    Pass export_to=None to skip writing the draft case file (tests, a read-only host).
    """
    conversation = store.one(
        "SELECT * FROM conversations WHERE conversation_id = :id", id=conversation_id
    )
    if conversation is None:
        raise ValueError(f"no conversation {conversation_id}")
    store.update(
        "conversations",
        {"conversation_id": conversation_id},
        feedback="up" if handled_well else "down",
    )
    # The queue is keyed by what is under review: a task id, or here a conversation id.
    store.execute("DELETE FROM eval_candidates WHERE cta_id = :id", id=conversation_id)
    if handled_well:
        return

    evidence = {
        "conversation_id": conversation_id,
        "account_id": conversation["account_id"],
        "prompt_version": conversation["prompt_version"],
        "answered_by": conversation["answered_by"],
        "outcome": conversation["outcome"],
        "reason_code": conversation["reason_code"],
        "transcript": json.loads(conversation["transcript"]),
    }
    store.insert(
        "eval_candidates",
        {
            "cta_id": conversation_id,
            "created_on": day,
            "source": THUMBS_DOWN,
            "reason_code": conversation["reason_code"],
            "human_notes": notes,
            "packet": json.dumps(evidence),
        },
    )
    if export_to is not None:
        export_to.mkdir(parents=True, exist_ok=True)
        case = {
            "id": f"feedback_{conversation_id}",
            "source": THUMBS_DOWN,
            "human_notes": notes,
            "expected_behavior": "to be written by the reviewer",
            "conversation": evidence,
            "status": "needs_review",  # a person turns it into a proper test case
        }
        path = export_to / f"{conversation_id}.json"
        path.write_text(json.dumps(case, indent=2), encoding="utf-8")
