"""The shape a product event must have to enter the warehouse.

Synthetic data, fictional company. This is the "schema on write" check: an event
that does not match is not loaded. It goes to the dead-letter queue with the
reason, so nothing is silently dropped. The same check is used for batch files
and for the webhook endpoint (Phase 7).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

EventName = Literal[
    "user_invited",
    "user_active",
    "board_created",
    "doc_published",
    "automation_rule_created",
    "integration_connected",
    "sso_configured",
    "assist_invoked",
    "admin_login",
]


class ProductEvent(BaseModel):
    event_id: str = Field(min_length=1)
    occurred_at: datetime
    account_id: str = Field(pattern=r"^A\d{4}$")  # the one id that joins everything
    user_id: str = Field(min_length=1)
    event_name: EventName
    properties: dict = Field(default_factory=dict)


def validate_event(line: str) -> tuple[ProductEvent | None, str | None, str | None]:
    """Check one raw JSON line.

    Returns (event, None, None) when it is valid, or (None, reason, detail) when
    it is not. `reason` is a short code we can count; `detail` is the full message.
    """
    try:
        return ProductEvent.model_validate_json(line), None, None
    except ValidationError as error:
        first = error.errors()[0]
        return None, _reason_code(first), first["msg"]


def _reason_code(error: dict) -> str:
    """Turn a validation error into a short, countable reason."""
    if error["type"] == "json_invalid":
        return "malformed_json"
    field = str(error["loc"][0]) if error["loc"] else "event"
    if field == "account_id":
        return "missing_account_id" if error["input"] is None else "invalid_account_id"
    if field == "event_name":
        return "unknown_event_name"
    return f"invalid_{field}"
