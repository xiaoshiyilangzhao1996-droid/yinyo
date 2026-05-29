"""Durable event id store for gateway idempotency."""

from __future__ import annotations

import json
import os
import time
from threading import Lock

from .jsonl_store import append_jsonl


class JsonlEventStore:
    def __init__(self, path: str):
        self.path = path
        self._lock = Lock()
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._seen = self._load()

    def seen(self, event_key: str) -> bool:
        with self._lock:
            return event_key in self._seen

    def mark_seen(self, event_key: str) -> None:
        if not event_key:
            return
        with self._lock:
            if event_key in self._seen:
                return
            self._seen.add(event_key)
            append_jsonl(self.path, {"ts": time.time(), "event_key": event_key})

    def _load(self) -> set[str]:
        if not os.path.isfile(self.path):
            return set()
        seen: set[str] = set()
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                event_key = item.get("event_key")
                if event_key:
                    seen.add(event_key)
        return seen
