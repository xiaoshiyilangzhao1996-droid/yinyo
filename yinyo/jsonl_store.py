"""Thread-safe JSONL append/read helpers for runtime evidence files."""

from __future__ import annotations

import json
import os
import threading
from collections import defaultdict
from typing import Any


_LOCKS: dict[str, threading.Lock] = defaultdict(threading.Lock)


def append_jsonl(path: str, record: dict[str, Any]) -> None:
    """Append one JSON record as a complete line.

    Runtime evidence files are shared by gateway worker threads. Keeping this
    helper small and centralized prevents partial-line writes from making the
    1.0 evidence chain unverifiable.
    """

    resolved = os.path.abspath(path)
    os.makedirs(os.path.dirname(resolved), exist_ok=True)
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with _LOCKS[resolved]:
        with open(resolved, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()


def load_jsonl(path: str) -> list[dict[str, Any]]:
    if not os.path.isfile(path):
        return []
    records: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                records.append(item)
    return records
