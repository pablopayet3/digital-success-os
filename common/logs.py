"""Structured logs: one JSON object per line.

Synthetic data, fictional company. Plain text logs are fine for a person reading a
terminal. A hosted service is read by tools, and tools want fields: which request,
how long, what status. Every log line here is a JSON object with a time, a level, a
logger name, a message and any extra fields the caller adds.

    log = get_logger("api")
    log.info("request", extra={"fields": {"path": "/health", "status": 200, "ms": 3}})
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": datetime.now(UTC).isoformat(timespec="seconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
            **getattr(record, "fields", {}),
        }
        if record.exc_info:
            entry["error"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def get_logger(name: str) -> logging.Logger:
    """A logger that writes JSON lines to standard output (set up once per name)."""
    logger = logging.getLogger(f"dso.{name}")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger
