"""Outbound Feishu delivery boundary for gateway workers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .governance import redact_secrets


@dataclass
class OutboxResult:
    success: bool
    message_ids: list[str]
    fallback: bool = False
    error: str | None = None
    attempts: int = 1
    dead_letter: bool = False


class FeishuOutbox:
    """Wrap Feishu delivery side effects behind a narrow interface."""

    def __init__(self, adapter: Any, max_attempts: int = 2):
        self.adapter = adapter
        self.max_attempts = max(1, int(max_attempts))

    def mark_processing(self, message_id: str) -> bool:
        if not message_id:
            return False
        return bool(self.adapter.add_reaction(message_id))

    def clear_processing(self, message_id: str) -> bool:
        if not message_id:
            return False
        return bool(self.adapter.remove_reaction(message_id))

    def send_reply(
        self,
        chat_id: str,
        text: str,
        *,
        reply_to: str = "",
        files: list[str] | None = None,
        force_fallback: bool = False,
    ) -> OutboxResult:
        if not text and not files:
            return OutboxResult(success=True, message_ids=[], attempts=0)

        last_error = None
        last_result: dict[str, Any] = {}
        for attempt in range(1, self.max_attempts + 1):
            try:
                result = self.adapter.send_message(
                    chat_id,
                    text,
                    reply_to=reply_to or None,
                    files=files or [],
                    force_fallback=force_fallback,
                )
            except TypeError:
                result = self.adapter.send_message(chat_id, text, reply_to=reply_to or None, files=files or [])
                if force_fallback and result.get("success"):
                    result["fallback"] = True
            except Exception as exc:
                result = {"success": False, "message_ids": [], "error": _safe_error(str(exc))}

            result = _redact_delivery_result(result)
            last_result = result
            last_error = result.get("error")
            if result.get("success"):
                return OutboxResult(
                    success=True,
                    message_ids=[m for m in result.get("message_ids", []) if m],
                    fallback=bool(result.get("fallback")),
                    error=result.get("error"),
                    attempts=attempt,
                    dead_letter=False,
                )

        return OutboxResult(
            success=False,
            message_ids=[m for m in last_result.get("message_ids", []) if m],
            fallback=bool(last_result.get("fallback")),
            error=last_error or "outbox delivery failed",
            attempts=self.max_attempts,
            dead_letter=True,
        )


def _redact_delivery_result(result: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(result)
    if cleaned.get("error") not in (None, ""):
        cleaned["error"] = _safe_error(str(cleaned["error"]))
    return cleaned


def _safe_error(value: str) -> str:
    return redact_secrets(value)
