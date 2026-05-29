"""Feishu-native runtime gateway.

This is intentionally not a multi-platform gateway. It gives the Feishu product
path a real runtime boundary: verification, normalization, idempotency, job
dispatch, and outbound delivery.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .jobs import InMemoryJobQueue, RuntimeJob
from .outbox import FeishuOutbox


_AT_MENTION_RE = re.compile(r'<at\s+user_id=["\']([^"\']+)["\'][^>]*>[^<]*</at>')
SMOKE_CARD_FALLBACK_COMMAND = "/yinyo-smoke card-fallback"


@dataclass
class GatewayResult:
    status_code: int
    body: dict[str, Any]
    job_id: str | None = None
    duplicate: bool = False


class FeishuRuntimeGateway:
    """Runtime boundary between Feishu events and the agent loop."""

    def __init__(
        self,
        *,
        adapter: Any,
        agent: Any = None,
        verify_token: str = "",
        queue: InMemoryJobQueue | None = None,
        outbox: FeishuOutbox | None = None,
        event_store: Any = None,
        logger: Any = None,
        smoke_recorder: Any = None,
        smoke_mode: bool = False,
    ):
        self.adapter = adapter
        self.agent = agent if agent is not None else getattr(adapter, "agent", None)
        self.verify_token = verify_token
        self.queue = queue or InMemoryJobQueue()
        self.outbox = outbox or FeishuOutbox(adapter)
        self.event_store = event_store
        self.logger = logger
        self.smoke_recorder = smoke_recorder
        self.smoke_mode = bool(smoke_mode)
        self._seen_event_keys: set[str] = set()

    def handle_event(self, event: dict[str, Any], *, async_dispatch: bool = True) -> GatewayResult:
        if event.get("type") == "url_verification":
            token = event.get("token", "")
            if self.verify_token and token != self.verify_token:
                self._log("webhook_rejected", correlation_id="", reason="bad_verify_token", event_type="url_verification")
                return GatewayResult(403, {})
            self._log("webhook_url_verification", correlation_id="", event_type="url_verification")
            self._smoke("url_verification", "passed", live=True, challenge=event.get("challenge", ""))
            return GatewayResult(200, {"challenge": event.get("challenge", "")})

        if event.get("type") != "event_callback":
            return GatewayResult(200, {})

        token = event.get("token", "")
        if self.verify_token and token and token != self.verify_token:
            self._log("webhook_rejected", correlation_id="", reason="bad_verify_token", event_type="event_callback")
            return GatewayResult(403, {})

        payload = self._normalize_event(event)
        if not payload:
            return GatewayResult(200, {})

        event_key = payload["event_key"]
        if self._has_seen(event_key):
            self._log("webhook_duplicate", correlation_id=event_key, event_key=event_key)
            self._smoke("duplicate_callback", "passed", live=True, event_key=event_key)
            return GatewayResult(200, {}, duplicate=True)

        job = self.queue.enqueue(
            "feishu_message",
            payload,
            self._process_message,
            run_async=async_dispatch,
        )
        if job.status == "rejected":
            self._log(
                "webhook_rejected",
                correlation_id=event_key,
                event_key=event_key,
                job_id=job.id,
                reason="queue_saturated",
                async_dispatch=async_dispatch,
            )
            return GatewayResult(503, {"error": "queue_saturated"}, job_id=job.id)

        self._mark_seen(event_key)
        self._log(
            "webhook_accepted",
            correlation_id=event_key,
            event_key=event_key,
            job_id=job.id,
            async_dispatch=async_dispatch,
        )
        return GatewayResult(200, {}, job_id=job.id)

    def get_job(self, job_id: str) -> RuntimeJob | None:
        return self.queue.get(job_id)

    def _normalize_event(self, event: dict[str, Any]) -> dict[str, Any] | None:
        inner = event.get("event", {})
        msg = inner.get("message", {})
        msg_type = msg.get("message_type", "text")
        message_id = msg.get("message_id", "")
        event_id = event.get("uuid") or event.get("event_id") or inner.get("event_id") or message_id
        if not event_id:
            return None

        return {
            "event_key": event_id,
            "message_type": msg_type,
            "content": msg.get("content", ""),
            "chat_id": msg.get("chat_id", ""),
            "message_id": message_id,
            "root_message_id": msg.get("root_id", ""),
            "user_id": inner.get("sender", {}).get("sender_id", {}).get("open_id", ""),
        }

    def _process_message(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.agent:
            return {"ok": False, "error": "agent not configured"}

        msg_type = payload.get("message_type")
        if msg_type == "text":
            text = self._extract_text(payload.get("content", ""))
        elif msg_type == "image":
            text = self._extract_image_text(payload.get("content", ""))
        else:
            return {"ok": False, "error": f"unsupported message type: {msg_type}"}

        if not text:
            return {"ok": False, "error": "empty message"}

        user_id = payload.get("user_id", "")
        chat_id = payload.get("chat_id", "")
        message_id = payload.get("message_id", "")
        reply_to = message_id or payload.get("root_message_id", "")
        smoke_probe = self.smoke_mode and text.strip().lower() == SMOKE_CARD_FALLBACK_COMMAND

        if not smoke_probe and self.agent.session_manager.is_duplicate(text, user_id):
            return {"ok": True, "duplicate": True}

        self.outbox.mark_processing(message_id)
        try:
            if smoke_probe:
                result = {
                    "text": "YINYO live smoke card fallback probe.",
                    "files": [],
                    "run_id": "smoke-card-fallback",
                }
                self._log(
                    "smoke_probe",
                    correlation_id=payload.get("event_key", ""),
                    scenario="card_fallback",
                )
            else:
                result = self.agent.handle_message(
                    user_id,
                    chat_id,
                    text,
                    already_deduped=True,
                    correlation_id=payload.get("event_key", ""),
                )
        except Exception as exc:
            self._log(
                "agent_message_failed",
                correlation_id=payload.get("event_key", ""),
                error_type=type(exc).__name__,
            )
            result = {
                "text": "YINYO could not complete this request. The operator evidence records contain the failure type.",
                "files": [],
            }
        finally:
            self.outbox.clear_processing(message_id)

        if result is None:
            return {"ok": True, "sent": False}

        delivery = self.outbox.send_reply(
            chat_id,
            result.get("text", ""),
            reply_to=reply_to,
            files=result.get("files", []),
            force_fallback=smoke_probe,
        )
        self._log(
            "outbox_delivery",
            correlation_id=payload.get("event_key", ""),
            success=delivery.success,
            message_ids=delivery.message_ids,
            fallback=delivery.fallback,
            error=delivery.error,
            attempts=delivery.attempts,
            dead_letter=delivery.dead_letter,
            run_id=result.get("run_id", "") if isinstance(result, dict) else "",
        )
        smoke_scenario = "image_message_reply" if msg_type == "image" else "text_message_reply"
        smoke_status = "passed" if delivery.success else "failed"
        self._smoke(
            smoke_scenario,
            smoke_status,
            live=True,
            event_key=payload.get("event_key", ""),
            message_type=msg_type,
            message_ids=delivery.message_ids,
            error=delivery.error,
            attempts=delivery.attempts,
            dead_letter=delivery.dead_letter,
        )
        if delivery.fallback:
            self._smoke(
                "card_fallback",
                smoke_status,
                live=True,
                event_key=payload.get("event_key", ""),
                message_type=msg_type,
                message_ids=delivery.message_ids,
                error=delivery.error,
                attempts=delivery.attempts,
                dead_letter=delivery.dead_letter,
            )
        return {
            "ok": delivery.success,
            "sent": bool(delivery.message_ids) or delivery.success,
            "message_ids": delivery.message_ids,
            "fallback": delivery.fallback,
            "error": delivery.error,
            "attempts": delivery.attempts,
            "dead_letter": delivery.dead_letter,
            "run_id": result.get("run_id", "") if isinstance(result, dict) else "",
        }

    def _extract_text(self, content: str) -> str:
        try:
            text = json.loads(content or "{}").get("text", "")
        except json.JSONDecodeError:
            text = content or ""
        return _AT_MENTION_RE.sub(r"@open_id:\1", text)

    def _extract_image_text(self, content: str) -> str:
        image_key = content
        if isinstance(image_key, str):
            try:
                image_key = json.loads(image_key).get("image_key", image_key)
            except json.JSONDecodeError:
                pass

        image_path = self.adapter._download_image(image_key) or image_key
        try:
            from .vision_adapter import get_vision_adapter

            vision_result = get_vision_adapter().describe(image_path, "Describe the image contents in detail.")
            description = vision_result.get("description", "")
            if vision_result.get("error"):
                description = f"[Image received but vision failed: {vision_result['error']}]"
        except Exception as exc:
            description = f"[Image received but vision failed: {exc}]"
        return f"[Image message received]\n{description}"

    def _has_seen(self, event_key: str) -> bool:
        if self.event_store:
            return self.event_store.seen(event_key)
        return event_key in self._seen_event_keys

    def _mark_seen(self, event_key: str) -> None:
        self._seen_event_keys.add(event_key)
        if self.event_store:
            self.event_store.mark_seen(event_key)

    def _log(self, event: str, *, correlation_id: str = "", **fields: Any) -> None:
        if self.logger:
            self.logger.record(event, correlation_id=correlation_id, **fields)

    def _smoke(self, scenario: str, status: str, **fields: Any) -> None:
        if self.smoke_recorder:
            self.smoke_recorder.record(scenario, status, **fields)
