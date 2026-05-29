"""Structured runtime logging for deployable service mode."""

from __future__ import annotations

import os
import time
from typing import Any

from .jsonl_store import append_jsonl


class RuntimeLogger:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    def record(self, event: str, *, correlation_id: str = "", **fields: Any) -> dict[str, Any]:
        entry = {
            "ts": time.time(),
            "event": event,
            "correlation_id": correlation_id,
            **fields,
        }
        append_jsonl(self.path, entry)
        return entry
