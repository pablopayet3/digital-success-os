"""Decide who gets a play and who is held out, without a random number generator.

Synthetic data, fictional company.

The decision comes from a hash of (account, play, version). The same account
always lands in the same group for the same version of a play, on any machine,
on any day. Nobody can nudge an account into treatment, and re-running the
engine never reshuffles the groups. Bumping the play's version reshuffles them
on purpose.
"""

from __future__ import annotations

import hashlib

SLICE_SHARE = 0.10  # rollout_stage "slice" = 10% of eligible accounts


def bucket(*parts: str) -> float:
    """A number from 0 to 1 that is always the same for the same inputs."""
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return int(digest[:16], 16) / 16**16


def assign_arm(account_id: str, play) -> str:
    """'holdout' for a share of accounts equal to the play's holdout_pct, else 'treatment'."""
    position = bucket(account_id, play.id, str(play.version), "holdout")
    return "holdout" if position < play.holdout_pct else "treatment"


def in_rollout(account_id: str, play) -> bool:
    """A play on a 'slice' only reaches 10% of eligible accounts. 'full' reaches all."""
    if play.rollout_stage == "full":
        return True
    return bucket(account_id, play.id, str(play.version), "slice") < SLICE_SHARE
