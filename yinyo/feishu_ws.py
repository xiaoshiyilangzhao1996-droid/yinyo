"""Feishu long-connection transport using the official server SDK."""

from __future__ import annotations

import json
import time
from typing import Any, Callable


class FeishuLongConnectionTransport:
    """Adapter boundary for Feishu WebSocket event delivery.

    The runtime gateway remains the product boundary. This class only translates
    official SDK event callbacks into the same event dictionary handled by the
    HTTP webhook path.
    """

    def __init__(
        self,
        *,
        adapter: Any,
        app_id: str,
        app_secret: str,
        logger: Any = None,
        ack_deadline_seconds: float = 3.0,
        ws_sdk_session_id: str = "",
    ):
        self.adapter = adapter
        self.app_id = app_id
        self.app_secret = app_secret
        self.logger = logger
        self.ack_deadline_seconds = float(ack_deadline_seconds)
        self.ws_sdk_session_id = str(ws_sdk_session_id or "").strip()
        self.client = None

    def handle_event(self, event: Any) -> tuple[int, dict[str, Any]]:
        started = time.perf_counter()
        payload = normalize_ws_event(event)
        result = self.adapter.gateway.handle_event(payload, async_dispatch=True)
        ack_latency_ms = round((time.perf_counter() - started) * 1000, 3)
        ack_deadline_ms = round(self.ack_deadline_seconds * 1000, 3)
        if self.logger:
            event_key = payload.get("uuid") or payload.get("event", {}).get("message", {}).get("message_id", "")
            self.logger.record(
                "ws_event_received",
                correlation_id=event_key,
                event_key=event_key,
                event_type=payload.get("type", ""),
                status_code=result.status_code,
                duplicate=result.duplicate,
                job_id=result.job_id or "",
                ack_latency_ms=ack_latency_ms,
                ack_deadline_ms=ack_deadline_ms,
                ack_within_deadline=ack_latency_ms <= ack_deadline_ms,
            )
        return result.status_code, result.body

    def start(self, *, client_factory: Callable[..., Any] | None = None) -> None:
        factory = client_factory or _default_client_factory
        self.client = factory(
            app_id=self.app_id,
            app_secret=self.app_secret,
            event_handler=self.handle_event,
        )
        if self.logger:
            fields = {"correlation_id": "service"}
            if self.ws_sdk_session_id:
                fields["ws_sdk_session_id"] = self.ws_sdk_session_id
            self.logger.record("ws_transport_start", **fields)
        self.client.start()


def normalize_ws_event(event: Any) -> dict[str, Any]:
    """Normalize SDK event objects or dict payloads into gateway input."""

    if isinstance(event, dict):
        payload = event
    elif hasattr(event, "to_dict"):
        payload = event.to_dict()
    elif hasattr(event, "raw"):
        payload = _loads(event.raw)
    elif hasattr(event, "data"):
        payload = _loads(event.data)
    else:
        payload = _object_payload(event) or _loads(str(event))

    if payload.get("type") in {"url_verification", "event_callback"}:
        return payload

    inner = payload.get("event", payload)
    header = payload.get("header", {})
    event_key = (
        header.get("event_id")
        or payload.get("uuid")
        or payload.get("event_id")
        or inner.get("event_id")
        or inner.get("message", {}).get("message_id")
        or ""
    )
    return {
        "type": "event_callback",
        "uuid": event_key,
        "token": payload.get("token", ""),
        "event": inner,
    }


def _loads(value: Any) -> dict[str, Any]:
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return loaded if isinstance(loaded, dict) else {}
    return value if isinstance(value, dict) else {}


def _object_payload(value: Any) -> dict[str, Any]:
    """Best-effort conversion for SDK event wrappers with header/event attrs."""
    if isinstance(value, dict):
        return value
    payload: dict[str, Any] = {}
    for attr in ("schema", "header", "event", "body", "token", "uuid", "event_id", "type"):
        if not hasattr(value, attr):
            continue
        item = _plain_value(getattr(value, attr))
        if item not in (None, "", [], {}):
            payload[attr] = item
    return payload


def _plain_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {str(key): _plain_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_value(item) for item in value]
    if hasattr(value, "to_dict"):
        try:
            loaded = value.to_dict()
        except Exception:
            loaded = None
        if isinstance(loaded, dict):
            return _plain_value(loaded)
    nested = {}
    for attr in ("event_id", "message", "sender", "message_type", "content", "chat_id", "message_id"):
        if hasattr(value, attr):
            item = _plain_value(getattr(value, attr))
            if item not in (None, "", [], {}):
                nested[attr] = item
    return nested


def _default_client_factory(*, app_id: str, app_secret: str, event_handler: Callable[[Any], Any]) -> Any:
    try:
        import lark_oapi as lark
    except ImportError as exc:
        raise RuntimeError("lark-oapi is required for Feishu long-connection transport") from exc

    def dispatch_sdk_event(data: Any) -> Any:
        return event_handler(_marshal_sdk_event(lark, data))

    dispatcher = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(dispatch_sdk_event)
        .build()
    )
    kwargs = {"event_handler": dispatcher}
    if hasattr(lark, "LogLevel"):
        kwargs["log_level"] = lark.LogLevel.INFO
    return lark.ws.Client(app_id, app_secret, **kwargs)


def _marshal_sdk_event(lark: Any, data: Any) -> dict[str, Any]:
    if hasattr(lark, "JSON") and hasattr(lark.JSON, "marshal"):
        marshalled = lark.JSON.marshal(data)
        loaded = _loads(marshalled)
        if loaded:
            return loaded
    return normalize_ws_event(data)
