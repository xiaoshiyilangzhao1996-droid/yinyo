# test_p4_service.py — P4 deployable service acceptance checks

import json
import os
import re
import subprocess
import sys
import hashlib


def _record_advanced_live_evidence(smoke_recorder):
    from yinyo import record_advanced_live_evidence

    record_advanced_live_evidence(smoke_recorder.path, "image_understanding", image_ref="image-redacted-1")
    record_advanced_live_evidence(smoke_recorder.path, "long_conversation", transcript_ref="redacted-transcript-1")
    record_advanced_live_evidence(smoke_recorder.path, "memory_supersession", memory_ref="mem-redacted-1")
    record_advanced_live_evidence(
        smoke_recorder.path,
        "trace2skill_promotion",
        failure_trace_ref="failure-trace-redacted-1",
        skill_ref="skill-retry-file-write",
        validation_ref="validation-redacted-1",
        promotion_status="proven",
        post_promotion_run_ref="post-promotion-run-redacted-1",
    )
    record_advanced_live_evidence(
        smoke_recorder.path,
        "deepseek_usage",
        model_usage={"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
    )
    record_advanced_live_evidence(smoke_recorder.path, "partial_failure", failure_ref="failure-redacted-1")


def _record_ws_runtime_evidence(
    logger,
    correlation_id="evt_bundle_target_ws_text",
    *,
    event_keys=None,
    ack_within_deadline=True,
    smoke_mode=False,
    ws_sdk_session_id="",
    service_start_offset_seconds=-60,
):
    import time

    workspace = os.path.dirname(os.path.abspath(logger.path))
    logger.record(
        "service_start",
        correlation_id="service",
        ts=time.time() + service_start_offset_seconds,
        profile="local",
        transport="ws",
        host="0.0.0.0",
        port=8080,
        workspace=workspace,
        default_model="deepseek-v4-flash",
        model_timeout_seconds=120,
        model_retry_count=1,
        model_retry_backoff_seconds=0.5,
        ack_deadline_seconds=3.0,
        max_steps=50,
        smoke_mode=smoke_mode,
        event_store_path=os.path.join(workspace, "gateway_events.jsonl"),
        job_store_path=os.path.join(workspace, "runtime_jobs.jsonl"),
        log_path=os.path.join(workspace, "runtime.jsonl"),
        smoke_evidence_path=os.path.join(workspace, "smoke_evidence.jsonl"),
        runtime_lock_path=os.path.join(workspace, "yinyo_runtime.lock"),
        ws_sdk_session_id=ws_sdk_session_id,
    )
    logger.record("ws_transport_start", correlation_id="service", ws_sdk_session_id=ws_sdk_session_id)
    keys = list(event_keys or [correlation_id])
    for index, event_key in enumerate(keys, start=1):
        logger.record(
            "ws_event_received",
            correlation_id=event_key,
            event_key=event_key,
            event_type="event_callback",
            status_code=200,
            duplicate=False,
            job_id=f"job-redacted-{index}",
            ack_latency_ms=12.5 if ack_within_deadline else 3100.0,
            ack_deadline_ms=3000.0,
            ack_within_deadline=ack_within_deadline,
        )


def _smoke_event_keys(gateway):
    return [
        str(item.get("event_key", ""))
        for item in json.loads("[" + ",".join([
            line
            for line in open(gateway.smoke_recorder.path, encoding="utf-8").read().splitlines()
            if line.strip()
        ]) + "]")
        if item.get("scenario") in {"text_message_reply", "image_message_reply", "card_fallback", "duplicate_callback"}
        and item.get("event_key")
    ]


def _write_replayable_handoff(run_dir, *, run_id, correlation_id, task="bundle handoff"):
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "evidence.jsonl").write_text("", encoding="utf-8")
    (run_dir / "manifest.json").write_text(json.dumps({"run_id": run_id}), encoding="utf-8")
    payload = {
        "schema": "yinyo.handoff.v1",
        "run_id": run_id,
        "correlation_id": correlation_id,
        "task": task,
        "status": "success",
        "intent": {"original_task": task, "final_status": "success"},
        "constraints": {"workspace": str(run_dir.parent.parent), "max_steps": 2, "max_runtime_seconds": 120},
        "permissions": {"confirm_tools_require_structured_metadata": True},
        "artifacts": {
            "evidence_file": f"runs/{run_id}/evidence.jsonl",
            "manifest_file": f"runs/{run_id}/manifest.json",
        },
        "provenance": {
            "source_audit": {"required": False, "satisfied": True},
            "model_usage": {},
        },
        "budget_state": {
            "max_steps": 2,
            "steps_used": 1,
            "steps_remaining": 1,
            "max_runtime_seconds": 120,
            "model_usage": {},
        },
        "trace_history": {
            "correlation_id": correlation_id,
            "evidence_hashes": [],
            "tools_used": [],
            "model_errors": [],
        },
        "risk": {"risk_notes": []},
        "unresolved": [],
    }
    (run_dir / "handoff.json").write_text(json.dumps(payload), encoding="utf-8")


def test_runtime_config_validation_redacts_secrets(tmp_path):
    from yinyo import ConfigError, RuntimeConfig, redact_config

    cfg = RuntimeConfig.load(workspace=str(tmp_path), app_secret="sk-secret-value")

    try:
        cfg.validate(require_secrets=True)
    except ConfigError as exc:
        msg = str(exc)
    else:
        raise AssertionError("expected ConfigError")

    assert "app_id" in msg
    assert "deepseek_api_key" in msg
    assert "sk-secret-value" not in msg
    redacted = redact_config(RuntimeConfig(
        workspace=str(tmp_path),
        app_id="app",
        app_secret="secret",
        verify_token="token",
        deepseek_api_key="sk-key",
    ))
    assert redacted["app_secret"] == "***"
    assert redacted["verify_token"] == "***"
    assert redacted["deepseek_api_key"] == "***"

    ws_without_verify_token = RuntimeConfig.load(
        workspace=str(tmp_path),
        transport="ws",
        app_id="app",
        app_secret="secret",
        deepseek_api_key="sk-test",
    )
    ws_without_verify_token.validate(require_secrets=True)

    http_without_verify_token = RuntimeConfig.load(
        workspace=str(tmp_path),
        transport="http",
        app_id="app",
        app_secret="secret",
        deepseek_api_key="sk-test",
    )
    try:
        http_without_verify_token.validate(require_secrets=True)
    except ConfigError as exc:
        http_msg = str(exc)
    else:
        raise AssertionError("expected HTTP config to require verify_token")

    assert "verify_token" in http_msg


def test_runtime_config_rejects_placeholder_live_secret_values(tmp_path):
    from yinyo import ConfigError, RuntimeConfig

    cfg = RuntimeConfig.load(
        workspace=str(tmp_path),
        transport="http",
        app_id="<app-id>",
        app_secret="secret",
        verify_token="xxx",
        deepseek_api_key="sk-test",
    )

    try:
        cfg.validate(require_secrets=True)
    except ConfigError as exc:
        msg = str(exc)
    else:
        raise AssertionError("expected placeholder runtime config to fail")

    assert "Placeholder runtime config values are not allowed for live smoke" in msg
    assert "app_id" in msg
    assert "verify_token" in msg
    assert "<app-id>" not in msg
    assert "sk-test" not in msg


def test_runtime_config_loads_key_value_file_and_defaults(tmp_path):
    from yinyo import RuntimeConfig

    config_path = tmp_path / "yinyo.env"
    config_path.write_text(
        "\n".join([
            f"workspace={tmp_path}",
            "profile=staging",
            "transport=http",
            "host=127.0.0.1",
            "port=9090",
            "app_id=app_id",
            "app_secret=app_secret",
            "verify_token=verify_token",
            "deepseek_api_key=deepseek_key",
            "model_timeout_seconds=11",
            "model_retry_count=2",
            "model_retry_backoff_seconds=0.5",
            "smoke_mode=true",
        ]),
        encoding="utf-8",
    )

    cfg = RuntimeConfig.load(str(config_path))

    assert cfg.host == "127.0.0.1"
    assert cfg.profile == "staging"
    assert cfg.transport == "http"
    assert cfg.port == 9090
    assert cfg.model_timeout_seconds == 11
    assert cfg.model_retry_count == 2
    assert cfg.model_retry_backoff_seconds == 0.5
    assert cfg.smoke_mode is True
    assert cfg.feishu_config()["smoke_mode"] is True
    assert cfg.event_store_path.endswith("gateway_events.jsonl")
    assert cfg.job_store_path.endswith("runtime_jobs.jsonl")
    assert cfg.runtime_lock_path.endswith("yinyo_runtime.lock")
    cfg.validate(require_secrets=True)

    bom_config = tmp_path / "yinyo-bom.env"
    bom_config.write_bytes(
        "\n".join([
            f"workspace={tmp_path}",
            "transport=ws",
            "app_id=app",
            "app_secret=secret",
            "deepseek_api_key=sk-test",
        ]).encode("utf-8-sig")
    )
    bom = RuntimeConfig.load(str(bom_config))
    assert bom.workspace == str(tmp_path)
    bom.validate(require_secrets=True)


def test_runtime_config_defaults_to_ws_and_validates_production_profile(tmp_path):
    from yinyo import ConfigError, RuntimeConfig

    local = RuntimeConfig.load(workspace=str(tmp_path))

    assert local.profile == "local"
    assert local.transport == "ws"
    assert local.ack_deadline_seconds == 3.0

    production = RuntimeConfig.load(
        workspace=str(tmp_path),
        profile="production",
        transport="ws",
        host="127.0.0.1",
        app_id="app",
        app_secret="secret",
        verify_token="token",
        deepseek_api_key="sk-test",
    )

    try:
        production.validate(require_secrets=True)
    except ConfigError as exc:
        msg = str(exc)
    else:
        raise AssertionError("expected production localhost validation error")

    assert "production profile" in msg

    slow_ack = RuntimeConfig.load(
        workspace=str(tmp_path),
        transport="ws",
        ack_deadline_seconds=4,
        app_id="app",
        app_secret="secret",
        verify_token="token",
        deepseek_api_key="sk-test",
        smoke_mode=True,
    )
    try:
        slow_ack.validate(require_secrets=True)
    except ConfigError as exc:
        msg = str(exc)
    else:
        raise AssertionError("expected ws ack deadline validation error")

    assert "ack_deadline_seconds <= 3" in msg


def test_runtime_config_rejects_smoke_mode_in_production(tmp_path):
    from yinyo import ConfigError, RuntimeConfig

    cfg = RuntimeConfig.load(
        workspace=str(tmp_path),
        profile="production",
        transport="ws",
        host="0.0.0.0",
        app_id="app",
        app_secret="secret",
        verify_token="token",
        deepseek_api_key="sk-test",
        model_retry_count=1,
        smoke_mode=True,
    )

    try:
        cfg.validate(require_secrets=True)
    except ConfigError as exc:
        msg = str(exc)
    else:
        raise AssertionError("expected production smoke_mode validation error")

    assert "must not enable smoke_mode" in msg


def test_config_template_is_secret_free_and_loadable(tmp_path):
    from yinyo import RuntimeConfig, build_config_template

    template = build_config_template(workspace=str(tmp_path / "workspace"))

    assert "app_secret=" in template
    assert "deepseek_api_key=" in template
    assert "Put raw secrets only in this local file or environment variables." in template
    assert "rotate it before release" in template
    assert "sk-" not in template
    assert "smoke_mode=false" in template
    assert "/yinyo-smoke card-fallback" not in template

    config_path = tmp_path / "yinyo.env"
    config_path.write_text(
        template
        + "\napp_id=app\napp_secret=secret\nverify_token=token\ndeepseek_api_key=sk-test\n",
        encoding="utf-8",
    )
    cfg = RuntimeConfig.load(str(config_path))

    assert cfg.transport == "ws"
    assert cfg.smoke_mode is False
    cfg.validate(require_secrets=True)


def test_config_template_live_smoke_mode_includes_operator_probe(tmp_path):
    from yinyo import RuntimeConfig, build_config_template

    template = build_config_template(live_smoke=True, workspace=str(tmp_path / "workspace"))
    config_path = tmp_path / "yinyo.env"
    config_path.write_text(
        template
        + "\napp_id=app\napp_secret=secret\nverify_token=token\ndeepseek_api_key=sk-test\n",
        encoding="utf-8",
    )
    cfg = RuntimeConfig.load(str(config_path))

    assert "smoke_mode=true" in template
    assert "/yinyo-smoke card-fallback" in template
    assert "Set smoke_mode=false" in template
    assert "yinyo smoke reset --config ./yinyo.env --confirm-reset" in template
    assert "yinyo smoke status --config ./yinyo.env --json" in template
    assert "yinyo smoke bundle --config ./yinyo.env --output ./workspace/smoke-bundle --handoff-dir ./workspace/runs" in template
    assert template.index("Set smoke_mode=false") < template.index("yinyo smoke bundle --config ./yinyo.env")
    assert "--live-attestation-id <attestation-id>" in template
    assert "--ws-sdk-session-id <ws-session-id>" not in template
    assert "Smoke bundle inherits this value" in template
    assert "python scripts/verify_release.py --target 1.0.0 --bundle ./workspace/smoke-bundle --candidate 1.0.0" in template
    assert "runtime_lock_path=" in template
    assert cfg.smoke_mode is True


def test_runtime_store_lock_blocks_second_local_writer(tmp_path):
    from yinyo import RuntimeLockError, RuntimeStoreLock, check_runtime_store_lock_available

    lock_path = tmp_path / "yinyo_runtime.lock"
    with RuntimeStoreLock(str(lock_path), owner="unit-test-owner"):
        ok, detail = check_runtime_store_lock_available(str(lock_path))
        assert ok is False
        assert "already held" in detail
        assert "unit-test-owner" in detail
        try:
            RuntimeStoreLock(str(lock_path)).acquire()
        except RuntimeLockError as exc:
            assert "unit-test-owner" in str(exc)
        else:
            raise AssertionError("expected second runtime lock to fail")

    ok, detail = check_runtime_store_lock_available(str(lock_path))
    assert ok is True
    assert detail.endswith("yinyo_runtime.lock")


def test_runtime_store_lock_recovers_stale_same_host_owner(tmp_path, monkeypatch):
    import socket
    import yinyo.runtime_lock as runtime_lock
    from yinyo import RuntimeStoreLock, check_runtime_store_lock_available

    lock_path = tmp_path / "yinyo_runtime.lock"
    stale_owner = f"pid=999999 host={socket.gethostname()} ts=1.000"
    lock_path.write_text(stale_owner + "\n", encoding="utf-8")
    monkeypatch.setattr(runtime_lock, "_pid_exists", lambda pid: False)

    ok, detail = check_runtime_store_lock_available(str(lock_path))

    assert ok is True
    assert "recovered stale owner" in detail
    assert stale_owner in detail
    assert not lock_path.exists()
    with RuntimeStoreLock(str(lock_path), owner="new-owner"):
        assert lock_path.read_text(encoding="utf-8").strip() == "new-owner"


def test_runtime_store_lock_does_not_recover_foreign_or_unknown_owner(tmp_path, monkeypatch):
    import yinyo.runtime_lock as runtime_lock
    from yinyo import RuntimeLockError, RuntimeStoreLock, check_runtime_store_lock_available

    lock_path = tmp_path / "yinyo_runtime.lock"
    lock_path.write_text("pid=999999 host=other-host ts=1.000\n", encoding="utf-8")
    monkeypatch.setattr(runtime_lock, "_pid_exists", lambda pid: False)

    ok, detail = check_runtime_store_lock_available(str(lock_path))

    assert ok is False
    assert "other-host" in detail
    try:
        RuntimeStoreLock(str(lock_path)).acquire()
    except RuntimeLockError as exc:
        assert "other-host" in str(exc)
    else:
        raise AssertionError("expected foreign lock to remain blocking")


def test_ws_event_normalization_and_transport_dispatch(tmp_path):
    from yinyo import FeishuLongConnectionTransport, RuntimeLogger, normalize_ws_event

    raw = {
        "schema": "2.0",
        "header": {"event_id": "evt_ws_1"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": "hello"}),
                "chat_id": "oc_1",
                "message_id": "om_1",
            },
        },
    }
    normalized = normalize_ws_event(raw)

    class Gateway:
        def __init__(self):
            self.events = []

        def handle_event(self, event, async_dispatch=True):
            self.events.append((event, async_dispatch))
            from yinyo import GatewayResult

            return GatewayResult(200, {}, job_id="job_1")

    class Adapter:
        gateway = Gateway()

    logger = RuntimeLogger(str(tmp_path / "runtime.jsonl"))
    transport = FeishuLongConnectionTransport(
        adapter=Adapter(),
        app_id="app",
        app_secret="secret",
        logger=logger,
        ws_sdk_session_id="session-live-transport-001",
    )
    started = []
    transport.start(client_factory=lambda **kwargs: type("Client", (), {"start": lambda self: started.append(kwargs)})())
    status_code, body = transport.handle_event(raw)

    assert normalized["type"] == "event_callback"
    assert normalized["uuid"] == "evt_ws_1"
    assert status_code == 200
    assert body == {}
    assert Adapter.gateway.events[0][0]["uuid"] == "evt_ws_1"
    assert Adapter.gateway.events[0][1] is True
    records = [
        json.loads(line)
        for line in (tmp_path / "runtime.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    ws_record = next(item for item in records if item["event"] == "ws_event_received")
    assert ws_record["ack_latency_ms"] >= 0
    assert ws_record["ack_deadline_ms"] == 3000.0
    assert ws_record["ack_within_deadline"] is True
    ws_start = next(item for item in records if item["event"] == "ws_transport_start")
    assert ws_start["ws_sdk_session_id"] == "session-live-transport-001"
    assert started[0]["app_id"] == "app"


def test_ws_event_normalization_accepts_attribute_wrapped_sdk_event():
    from yinyo import normalize_ws_event

    class Header:
        event_id = "evt_attr_1"

    class Message:
        message_type = "text"
        content = json.dumps({"text": "hello"})
        chat_id = "oc_attr"
        message_id = "om_attr"

    class Event:
        message = Message()

    class WrappedEvent:
        schema = "2.0"
        header = Header()
        event = Event()

    normalized = normalize_ws_event(WrappedEvent())

    assert normalized["type"] == "event_callback"
    assert normalized["uuid"] == "evt_attr_1"
    assert normalized["event"]["message"]["message_type"] == "text"
    assert normalized["event"]["message"]["message_id"] == "om_attr"


def test_serve_uses_long_connection_transport_for_ws(tmp_path, monkeypatch):
    from yinyo import RuntimeConfig
    import yinyo.service as service_module

    calls = []

    class Transport:
        def __init__(self, adapter, app_id, app_secret, logger=None, ack_deadline_seconds=0, ws_sdk_session_id=""):
            calls.append({
                "app_id": app_id,
                "app_secret": app_secret,
                "logger": logger,
                "ack_deadline_seconds": ack_deadline_seconds,
                "ws_sdk_session_id": ws_sdk_session_id,
            })

        def start(self):
            calls.append({"started": True})

    monkeypatch.setattr(service_module, "FeishuLongConnectionTransport", Transport)
    cfg = RuntimeConfig(
        workspace=str(tmp_path),
        transport="ws",
        app_id="app",
        app_secret="secret",
        verify_token="token",
        deepseek_api_key="sk-test",
        ws_sdk_session_id="session-live-serve-001",
    )
    cfg.apply_defaults()

    service_module.serve(cfg)

    assert calls[0]["app_id"] == "app"
    assert calls[0]["ack_deadline_seconds"] == 3.0
    assert calls[0]["ws_sdk_session_id"] == "session-live-serve-001"
    assert calls[-1] == {"started": True}
    records = [
        json.loads(line)
        for line in open(cfg.log_path, encoding="utf-8").read().splitlines()
    ]
    service_start = next(item for item in records if item["event"] == "service_start")
    assert service_start["profile"] == "local"
    assert service_start["transport"] == "ws"
    assert service_start["default_model"] == "deepseek-v4-flash"
    assert service_start["ack_deadline_seconds"] == 3.0
    assert service_start["ws_sdk_session_id"] == "session-live-serve-001"
    assert service_start["smoke_mode"] is False
    assert service_start["event_store_path"] == cfg.event_store_path
    assert service_start["job_store_path"] == cfg.job_store_path
    assert service_start["smoke_evidence_path"] == cfg.smoke_evidence_path
    service_stop = records[-1]
    assert service_stop["event"] == "service_stop"
    assert service_stop["status"] == "stopped"
    assert service_stop["transport"] == "ws"
    dumped = json.dumps(records, ensure_ascii=False)
    assert "secret" not in dumped
    assert "sk-test" not in dumped
    assert "token" not in dumped
    assert not os.path.exists(cfg.runtime_lock_path)


def test_serve_rejects_second_process_lock(tmp_path, monkeypatch):
    from yinyo import RuntimeConfig, RuntimeLockError, RuntimeStoreLock
    import yinyo.service as service_module

    started = []

    class Transport:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            started.append(True)

    monkeypatch.setattr(service_module, "FeishuLongConnectionTransport", Transport)
    cfg = RuntimeConfig(
        workspace=str(tmp_path),
        transport="ws",
        app_id="app",
        app_secret="secret",
        verify_token="token",
        deepseek_api_key="sk-test",
    )
    cfg.apply_defaults()

    with RuntimeStoreLock(cfg.runtime_lock_path, owner="other-worker"):
        try:
            service_module.serve(cfg)
        except RuntimeLockError as exc:
            msg = str(exc)
        else:
            raise AssertionError("expected service lock validation error")

    assert "other-worker" in msg
    assert started == []


def test_serve_records_failed_service_stop_without_secret_echo(tmp_path, monkeypatch):
    from yinyo import RuntimeConfig
    import yinyo.service as service_module

    class Transport:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            raise RuntimeError("secret sk-test token should not be logged")

    monkeypatch.setattr(service_module, "FeishuLongConnectionTransport", Transport)
    cfg = RuntimeConfig(
        workspace=str(tmp_path),
        transport="ws",
        app_id="app",
        app_secret="secret",
        verify_token="token",
        deepseek_api_key="sk-test",
    )
    cfg.apply_defaults()

    try:
        service_module.serve(cfg)
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected transport failure")

    records = [
        json.loads(line)
        for line in open(cfg.log_path, encoding="utf-8").read().splitlines()
    ]
    service_stop = records[-1]
    assert service_stop["event"] == "service_stop"
    assert service_stop["status"] == "failed"
    assert service_stop["error_type"] == "RuntimeError"
    dumped = json.dumps(records, ensure_ascii=False)
    assert "secret sk-test token" not in dumped
    assert "sk-test" not in dumped
    assert "token should not be logged" not in dumped
    assert not os.path.exists(cfg.runtime_lock_path)


def test_default_ws_client_factory_uses_official_sdk_contract(monkeypatch):
    import types
    from yinyo.feishu_ws import _default_client_factory

    calls = {}

    class Builder:
        def register_p2_im_message_receive_v1(self, callback):
            calls["callback"] = callback
            return self

        def build(self):
            return "dispatcher"

    class EventDispatcherHandler:
        @staticmethod
        def builder(encrypt_key, verification_token):
            calls["builder"] = (encrypt_key, verification_token)
            return Builder()

    class JSON:
        @staticmethod
        def marshal(data):
            return json.dumps(data)

    class Client:
        def __init__(self, app_id, app_secret, **kwargs):
            calls["client"] = (app_id, app_secret, kwargs)

        def start(self):
            calls["started"] = True

    fake_lark = types.SimpleNamespace(
        EventDispatcherHandler=EventDispatcherHandler,
        JSON=JSON,
        LogLevel=types.SimpleNamespace(INFO="info"),
        ws=types.SimpleNamespace(Client=Client),
    )
    received = []
    monkeypatch.setitem(sys.modules, "lark_oapi", fake_lark)

    client = _default_client_factory(
        app_id="app",
        app_secret="secret",
        event_handler=lambda event: received.append(event),
    )
    calls["callback"]({"header": {"event_id": "evt_1"}, "event": {"message": {"message_id": "om_1"}}})

    assert client is not None
    assert calls["builder"] == ("", "")
    assert calls["client"][0:2] == ("app", "secret")
    assert calls["client"][2]["event_handler"] == "dispatcher"
    assert calls["client"][2]["log_level"] == "info"
    assert received[0]["header"]["event_id"] == "evt_1"


def test_jsonl_event_store_survives_restart(tmp_path):
    from yinyo import JsonlEventStore

    store_path = tmp_path / "events.jsonl"
    first = JsonlEventStore(str(store_path))
    first.mark_seen("evt_1")

    second = JsonlEventStore(str(store_path))

    assert second.seen("evt_1")
    assert not second.seen("evt_2")


def test_jsonl_job_queue_persists_lifecycle_and_reload(tmp_path):
    from yinyo import JsonlJobQueue

    store_path = tmp_path / "jobs.jsonl"
    queue = JsonlJobQueue(str(store_path))
    job = queue.enqueue(
        "unit",
        {"value": 2},
        lambda payload: {"value": payload["value"] + 1},
        run_async=False,
    )

    reloaded = JsonlJobQueue(str(store_path))
    saved = reloaded.get(job.id)
    text = store_path.read_text(encoding="utf-8")

    assert saved is not None
    assert saved.status == "succeeded"
    assert saved.result == {"value": 3}
    assert '"event": "queued"' in text
    assert '"event": "succeeded"' in text


def test_jsonl_job_queue_marks_unfinished_jobs_abandoned_on_reload(tmp_path):
    import json
    import time
    from yinyo import JsonlJobQueue

    store_path = tmp_path / "jobs.jsonl"
    created = time.time() - 30
    store_path.write_text(
        json.dumps({
            "id": "job_unfinished",
            "kind": "unit",
            "payload": {"value": 1},
            "status": "running",
            "created_at": created,
            "started_at": created,
            "event": "running",
            "recorded_at": created,
        }) + "\n",
        encoding="utf-8",
    )

    queue = JsonlJobQueue(str(store_path))
    job = queue.get("job_unfinished")
    text = store_path.read_text(encoding="utf-8")

    assert job is not None
    assert job.status == "abandoned"
    assert job.finished_at is not None
    assert job.recovery_count == 1
    assert "abandoned_after_restart" in text
    assert "job abandoned after runtime restart before completion" in text


def test_jsonl_job_queue_rejects_when_async_workers_are_saturated(tmp_path):
    import threading
    from yinyo import JsonlJobQueue

    release = threading.Event()
    queue = JsonlJobQueue(str(tmp_path / "jobs.jsonl"), max_workers=1)

    first = queue.enqueue("unit", {"value": 1}, lambda payload: release.wait(timeout=5), run_async=True)
    second = queue.enqueue("unit", {"value": 2}, lambda payload: {"ok": True}, run_async=True)
    release.set()

    text = (tmp_path / "jobs.jsonl").read_text(encoding="utf-8")

    assert first.status in {"running", "succeeded"}
    assert second.status == "rejected"
    assert second.error == "job queue saturated"
    assert "rejected_queue_saturated" in text


def test_runtime_jsonl_writers_are_thread_safe(tmp_path):
    import threading

    from yinyo import JsonlEventStore, JsonlJobQueue, RuntimeLogger, SmokeEvidenceRecorder
    from yinyo.jsonl_store import load_jsonl

    runtime_path = tmp_path / "runtime.jsonl"
    smoke_path = tmp_path / "smoke.jsonl"
    event_path = tmp_path / "events.jsonl"
    job_path = tmp_path / "jobs.jsonl"
    logger = RuntimeLogger(str(runtime_path))
    smoke = SmokeEvidenceRecorder(str(smoke_path))
    events = JsonlEventStore(str(event_path))
    jobs = JsonlJobQueue(str(job_path))

    def write_batch(offset):
        for i in range(20):
            n = offset + i
            logger.record("concurrent_log", correlation_id=f"evt_{n}", index=n)
            smoke.record("text_message_reply", "passed", live=True, event_key=f"evt_{n}")
            events.mark_seen(f"evt_{n}")
            jobs.enqueue("unit", {"value": n}, lambda payload: {"value": payload["value"]}, run_async=False)

    threads = [threading.Thread(target=write_batch, args=(i * 20,)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(load_jsonl(str(runtime_path))) == 80
    assert len(load_jsonl(str(smoke_path))) == 80
    assert len(load_jsonl(str(event_path))) == 80
    assert len(load_jsonl(str(job_path))) == 80 * 4


def test_gateway_uses_durable_store_logs_and_smoke_evidence(tmp_path):
    from yinyo import FeishuRuntimeGateway, JsonlEventStore, RuntimeLogger, SmokeEvidenceRecorder

    class Session:
        def is_duplicate(self, text, user_id):
            return False

    class Agent:
        session_manager = Session()

        def handle_message(self, user_id, chat_id, text, already_deduped=False, correlation_id=""):
            return {"text": "ok", "files": []}

    class Adapter:
        agent = Agent()

        def add_reaction(self, message_id):
            return True

        def remove_reaction(self, message_id):
            return True

        def send_message(self, *args, **kwargs):
            return {"success": True, "message_ids": ["om_reply"], "fallback": bool(kwargs.get("files"))}

        def _download_image(self, image_key):
            return image_key

    gateway = FeishuRuntimeGateway(
        adapter=Adapter(),
        agent=Adapter.agent,
        verify_token="good-token",
        event_store=JsonlEventStore(str(tmp_path / "events.jsonl")),
        logger=RuntimeLogger(str(tmp_path / "runtime.jsonl")),
        smoke_recorder=SmokeEvidenceRecorder(str(tmp_path / "smoke.jsonl")),
    )
    event = {
        "type": "event_callback",
        "uuid": "evt_1",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": "hello"}),
                "chat_id": "oc_1",
                "message_id": "om_1",
            },
        },
    }

    accepted = gateway.handle_event(event, async_dispatch=False)
    duplicate_gateway = FeishuRuntimeGateway(
        adapter=Adapter(),
        agent=Adapter.agent,
        verify_token="good-token",
        event_store=JsonlEventStore(str(tmp_path / "events.jsonl")),
        logger=RuntimeLogger(str(tmp_path / "runtime.jsonl")),
    )
    duplicate = duplicate_gateway.handle_event(event, async_dispatch=False)

    assert accepted.job_id
    assert duplicate.duplicate is True
    log_text = (tmp_path / "runtime.jsonl").read_text(encoding="utf-8")
    smoke_text = (tmp_path / "smoke.jsonl").read_text(encoding="utf-8")
    assert "webhook_accepted" in log_text
    assert "outbox_delivery" in log_text
    assert "webhook_duplicate" in log_text
    assert "text_message_reply" in smoke_text
    assert '"live": true' in smoke_text


def test_build_service_wires_runtime_components(tmp_path):
    from yinyo import JsonlEventStore, JsonlJobQueue, RuntimeConfig, RuntimeLogger, SmokeEvidenceRecorder, build_service

    cfg = RuntimeConfig(
        workspace=str(tmp_path),
        app_id="app",
        app_secret="secret",
        verify_token="token",
        deepseek_api_key="sk-test",
        smoke_mode=True,
    )
    cfg.apply_defaults()

    adapter = build_service(cfg)

    assert adapter.agent.workspace == str(tmp_path)
    assert adapter.agent.model.timeout_seconds == cfg.model_timeout_seconds
    assert adapter.agent.model.retry_count == cfg.model_retry_count
    assert isinstance(adapter.gateway.queue, JsonlJobQueue)
    assert adapter.gateway.queue.max_workers == cfg.job_max_workers
    assert isinstance(adapter.gateway.event_store, JsonlEventStore)
    assert isinstance(adapter.gateway.logger, RuntimeLogger)
    assert isinstance(adapter.gateway.smoke_recorder, SmokeEvidenceRecorder)
    assert adapter.gateway.smoke_mode is True


def test_cli_serve_dry_run_validates_config_without_secret_echo(tmp_path):
    config_path = tmp_path / "runtime.env"
    config_path.write_text(
        "\n".join([
            f"workspace={tmp_path}",
            "transport=http",
            "app_id=app",
            "app_secret=super-secret",
            "verify_token=verify-secret",
            "deepseek_api_key=sk-secret",
        ]),
        encoding="utf-8",
    )

    env = dict(os.environ)
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env["PYTHONPATH"] = repo + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [sys.executable, "-m", "yinyo.cli", "serve", "--config", str(config_path), "--dry-run"],
        cwd=str(tmp_path),
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )

    assert result.returncode == 0
    assert "YINYO runtime config OK" in result.stdout
    assert "super-secret" not in result.stdout
    assert "verify-secret" not in result.stdout
    assert "sk-secret" not in result.stdout


def test_cli_config_template_outputs_live_smoke_template(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "config",
            "template",
            "--workspace",
            str(tmp_path / "workspace"),
            "--live-smoke",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert f"workspace={tmp_path / 'workspace'}" in result.stdout
    assert "smoke_mode=true" in result.stdout
    assert "/yinyo-smoke card-fallback" in result.stdout
    assert "sk-" not in result.stdout


def test_cli_serve_accepts_profile_and_transport_overrides(tmp_path):
    config_path = tmp_path / "runtime.env"
    config_path.write_text(
        "\n".join([
            f"workspace={tmp_path}",
            "profile=local",
            "transport=ws",
            "host=127.0.0.1",
            "app_id=app",
            "app_secret=super-secret",
            "verify_token=verify-secret",
            "deepseek_api_key=sk-secret",
        ]),
        encoding="utf-8",
    )

    env = dict(os.environ)
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env["PYTHONPATH"] = repo + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "serve",
            "--config",
            str(config_path),
            "--profile",
            "staging",
            "--transport",
            "http",
            "--dry-run",
        ],
        cwd=str(tmp_path),
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )

    assert result.returncode == 0
    assert "'profile': 'staging'" in result.stdout
    assert "'transport': 'http'" in result.stdout


def test_agent_run_writes_correlation_id_to_manifest_and_evidence(tmp_path):
    from yinyo import YinyoAgent

    agent = YinyoAgent(workspace=str(tmp_path), max_steps=3)
    agent.model.set_mock_responses([
        {"content": "[STEP 1] read file", "finish_reason": "stop"},
        {
            "content": "",
            "tool_calls": [{
                "id": "call_read",
                "type": "function",
                "function": {
                    "name": "do_read",
                    "arguments": json.dumps({"path": "probe.txt"}),
                },
            }],
            "finish_reason": "tool_calls",
        },
        {"content": "done", "finish_reason": "stop"},
        {"content": '{"reflections": [], "memory_add": [], "memory_update": [], "memory_remove": []}', "finish_reason": "stop"},
        {"content": "[]", "finish_reason": "stop"},
    ])
    (tmp_path / "probe.txt").write_text("hello", encoding="utf-8")

    result = agent.run("read probe", correlation_id="evt-correlation-1")

    manifest = json.loads((tmp_path / "runs" / result["run_id"] / "manifest.json").read_text(encoding="utf-8"))
    evidence = json.loads((tmp_path / result["evidence_file"]).read_text(encoding="utf-8").splitlines()[0])
    assert result["correlation_id"] == "evt-correlation-1"
    assert manifest["correlation_id"] == "evt-correlation-1"
    assert evidence["correlation_id"] == "evt-correlation-1"


def test_agent_run_records_model_usage_and_estimated_cost(tmp_path):
    from yinyo import YinyoAgent

    agent = YinyoAgent(workspace=str(tmp_path), max_steps=2)
    agent.model.set_mock_responses([
        {"content": "[STEP 1] answer", "finish_reason": "stop", "usage": {"prompt_tokens": 10, "completion_tokens": 2}},
        {"content": "done", "finish_reason": "stop", "usage": {"prompt_tokens": 20, "completion_tokens": 4}, "model": "deepseek-v4-flash"},
        {"content": '{"reflections": [], "memory_add": [], "memory_update": [], "memory_remove": []}', "finish_reason": "stop", "usage": {"prompt_tokens": 5, "completion_tokens": 1}},
        {"content": "[]", "finish_reason": "stop"},
    ])

    result = agent.run("record model usage")
    manifest = json.loads((tmp_path / "runs" / result["run_id"] / "manifest.json").read_text(encoding="utf-8"))

    assert result["model_usage"]["prompt_tokens"] == 35
    assert result["model_usage"]["completion_tokens"] == 7
    assert result["model_usage"]["total_tokens"] == 42
    assert result["model_usage"]["calls"] == 3
    assert result["model_usage"]["estimated_cost_usd"] > 0
    assert manifest["model_usage"] == result["model_usage"]


def test_gateway_passes_event_key_to_agent_correlation_id(tmp_path):
    from yinyo import FeishuRuntimeGateway

    class Session:
        def is_duplicate(self, text, user_id):
            return False

    class Agent:
        session_manager = Session()

        def __init__(self):
            self.calls = []

        def handle_message(self, user_id, chat_id, text, already_deduped=False, correlation_id=""):
            self.calls.append({
                "user_id": user_id,
                "chat_id": chat_id,
                "text": text,
                "already_deduped": already_deduped,
                "correlation_id": correlation_id,
            })
            return {"text": "ok", "files": [], "run_id": "run-1"}

    class Adapter:
        def add_reaction(self, message_id):
            return True

        def remove_reaction(self, message_id):
            return True

        def send_message(self, *args, **kwargs):
            return {"success": True, "message_ids": ["om_reply"], "fallback": bool(kwargs.get("files"))}

        def _download_image(self, image_key):
            return image_key

    agent = Agent()
    adapter = Adapter()
    adapter.agent = agent
    gateway = FeishuRuntimeGateway(adapter=adapter, agent=agent, verify_token="good-token")

    result = gateway.handle_event({
        "type": "event_callback",
        "uuid": "evt-correlation-2",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": "hello"}),
                "chat_id": "oc_1",
                "message_id": "om_1",
            },
        },
    }, async_dispatch=False)

    job = gateway.get_job(result.job_id)
    assert agent.calls[0]["correlation_id"] == "evt-correlation-2"
    assert job.result["run_id"] == "run-1"


def test_gateway_smoke_mode_forces_card_fallback_probe(tmp_path):
    from yinyo import FeishuRuntimeGateway, RuntimeLogger, SmokeEvidenceRecorder

    class Session:
        def is_duplicate(self, text, user_id):
            return False

    class Agent:
        session_manager = Session()

        def __init__(self):
            self.calls = []

        def handle_message(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return {"text": "agent should not be called", "files": []}

    class Adapter:
        def __init__(self):
            self.sent = []

        def add_reaction(self, message_id):
            return True

        def remove_reaction(self, message_id):
            return True

        def send_message(self, *args, **kwargs):
            self.sent.append({"args": args, "kwargs": kwargs})
            return {
                "success": True,
                "message_ids": ["om_smoke"],
                "fallback": bool(kwargs.get("force_fallback")),
            }

        def _download_image(self, image_key):
            return image_key

    agent = Agent()
    adapter = Adapter()
    adapter.agent = agent
    smoke_path = tmp_path / "smoke.jsonl"
    log_path = tmp_path / "runtime.jsonl"
    gateway = FeishuRuntimeGateway(
        adapter=adapter,
        agent=agent,
        verify_token="good-token",
        logger=RuntimeLogger(str(log_path)),
        smoke_recorder=SmokeEvidenceRecorder(str(smoke_path)),
        smoke_mode=True,
    )

    result = gateway.handle_event({
        "type": "event_callback",
        "uuid": "evt_smoke_card",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": "/yinyo-smoke card-fallback"}),
                "chat_id": "oc_1",
                "message_id": "om_1",
            },
        },
    }, async_dispatch=False)
    job = gateway.get_job(result.job_id)
    smoke_records = [json.loads(line) for line in smoke_path.read_text(encoding="utf-8").splitlines()]
    runtime_events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]

    assert agent.calls == []
    assert adapter.sent[0]["kwargs"]["force_fallback"] is True
    assert job.result["fallback"] is True
    assert job.result["run_id"] == "smoke-card-fallback"
    assert [record["scenario"] for record in smoke_records] == ["text_message_reply", "card_fallback"]
    assert any(event["event"] == "smoke_probe" for event in runtime_events)


def test_gateway_smoke_command_is_normal_text_when_smoke_mode_disabled():
    from yinyo import FeishuRuntimeGateway

    class Session:
        def is_duplicate(self, text, user_id):
            return False

    class Agent:
        session_manager = Session()

        def __init__(self):
            self.calls = []

        def handle_message(self, user_id, chat_id, text, **kwargs):
            self.calls.append(text)
            return {"text": "ok", "files": [], "run_id": "run-normal"}

    class Adapter:
        def add_reaction(self, message_id):
            return True

        def remove_reaction(self, message_id):
            return True

        def send_message(self, *args, **kwargs):
            return {"success": True, "message_ids": ["om_reply"], "fallback": False}

        def _download_image(self, image_key):
            return image_key

    agent = Agent()
    adapter = Adapter()
    adapter.agent = agent
    gateway = FeishuRuntimeGateway(adapter=adapter, agent=agent, verify_token="good-token", smoke_mode=False)

    result = gateway.handle_event({
        "type": "event_callback",
        "uuid": "evt_smoke_disabled",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": "/yinyo-smoke card-fallback"}),
                "chat_id": "oc_1",
                "message_id": "om_1",
            },
        },
    }, async_dispatch=False)

    assert agent.calls == ["/yinyo-smoke card-fallback"]
    assert gateway.get_job(result.job_id).result["fallback"] is False


def test_feishu_adapter_force_fallback_sends_text_without_card():
    from yinyo.feishu_adapter import FeishuAdapter

    class Adapter(FeishuAdapter):
        def __init__(self):
            super().__init__(agent=None, config={})
            self.card_calls = 0
            self.text_calls = 0

        def _send_card(self, chat_id, card, reply_to=None):
            self.card_calls += 1
            return {"success": True, "message_id": "om_card"}

        def _send_text(self, chat_id, text, reply_to=None):
            self.text_calls += 1
            return {"success": True, "message_id": "om_text", "fallback": True}

    adapter = Adapter()

    result = adapter.send_message("oc_1", "hello", reply_to="om_1", force_fallback=True)

    assert result["success"] is True
    assert result["message_ids"] == ["om_text"]
    assert result["fallback"] is True
    assert adapter.card_calls == 0
    assert adapter.text_calls == 1


def test_release_verifier_passes_current_alpha():
    import os
    import subprocess
    import sys

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [sys.executable, "scripts/verify_release.py"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Release verification passed" in result.stdout


def test_release_verifier_rejects_config_and_bundle_together(tmp_path):
    import os
    import subprocess
    import sys

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [
            sys.executable,
            "scripts/verify_release.py",
            "--target",
            "1.0.0",
            "--config",
            str(tmp_path / "yinyo.env"),
            "--bundle",
            str(tmp_path / "bundle"),
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "use either --config or --bundle" in result.stderr


def test_release_candidate_provenance_rejects_placeholder_tokens_and_malformed_hashes():
    import importlib.util
    import os

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location("verify_release", os.path.join(repo, "scripts", "verify_release.py"))
    verify_release = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verify_release)

    placeholder_manifest = {
        "runtime": {"transport": "ws"},
        "live_provenance": {
            "schema": "yinyo.live_provenance.v1",
            "operator_attestation_id": "real-attestation-001",
            "feishu_app_id_hash": "redacted-app",
            "tenant_hash": "test-tenant",
            "ws_sdk_session_id": "synthetic-session-1",
        },
    }
    malformed_manifest = {
        "runtime": {"transport": "ws"},
        "live_provenance": {
            "schema": "yinyo.live_provenance.v1",
            "operator_attestation_id": "real-attestation-001",
            "feishu_app_id_hash": "abc123",
            "tenant_hash": "def456",
            "ws_sdk_session_id": "session-live-001",
        },
    }

    assert verify_release._verify_live_provenance(placeholder_manifest) == [
        "candidate 1.0.0 requires live provenance fields: feishu_app_id_hash, tenant_hash, ws_sdk_session_id"
    ]
    assert verify_release._verify_live_provenance(malformed_manifest) == [
        "candidate 1.0.0 requires sha256 live provenance hashes: feishu_app_id_hash, tenant_hash"
    ]


def test_readiness_advanced_blockers_include_unresolved_refs():
    from yinyo.readiness import _advanced_blockers

    blockers = _advanced_blockers({
        "ok": False,
        "missing": [],
        "field_missing": [],
        "source_missing": [],
        "proof_missing": [],
        "proof_mismatch": [],
        "ref_unresolved": ["trace2skill_promotion:validation_ref"],
    })

    assert blockers == ["unresolved advanced live ref: trace2skill_promotion:validation_ref"]


def test_release_workflow_uses_shared_wheel_verifier():
    import os

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = open(os.path.join(repo, "scripts", "verify_wheel.py"), encoding="utf-8").read()
    workflow = open(os.path.join(repo, ".github", "workflows", "release.yml"), encoding="utf-8").read()
    ci = open(os.path.join(repo, ".github", "workflows", "test.yml"), encoding="utf-8").read()

    assert '"-m", "build"' in script
    assert '"pip", "install"' in script
    assert "Wheel verification passed" in script
    assert "SDIST_REQUIRED_FILES" in script
    assert "SUBPROCESS_TIMEOUT_SECONDS" in script
    assert "timeout" in script
    assert "tarfile.open" in script
    assert "docs/spec.md" in script
    assert "scripts/verify_release.py" in script
    assert "build_smoke_evidence_status" in script
    assert "verify_smoke_evidence_bundle" in script
    assert "_write_incomplete_runtime_evidence" in script
    assert '"live": True' not in script
    assert "missing required evidence fields" in script
    assert '"smoke", "status"' in script
    assert '"smoke", "plan"' in script
    assert '"diagnose"' in script
    assert "service: started=True, last_status=stopped" in script
    assert "bundle_digest" in script
    assert "importlib.metadata" in script
    assert "_expected_package_version" in script
    assert "expected_version =" in script
    assert "assert meta['Version'] == expected_version" in script
    assert "assert yinyo.__version__ == expected_version" in script
    assert "0.1.0a1" not in script
    assert "YINYO - a Feishu-native agent with memory, evidence, and release gates" in script
    assert "python -m build" in workflow
    assert "python -m build" in ci
    assert "python scripts/verify_wheel.py --skip-build" in workflow
    assert "python scripts/verify_wheel.py --skip-build" in ci


def test_wheel_verifier_rejects_stale_dist_artifacts(tmp_path):
    from scripts.verify_wheel import _select_release_artifacts

    dist = tmp_path / "dist"
    dist.mkdir()
    current_wheel = dist / "yinyo_agent-1.0.0rc1-py3-none-any.whl"
    current_sdist = dist / "yinyo_agent-1.0.0rc1.tar.gz"
    old_wheel = dist / "yinyo_agent-0.1.0a1-py3-none-any.whl"
    current_wheel.write_text("wheel", encoding="utf-8")
    current_sdist.write_text("sdist", encoding="utf-8")
    old_wheel.write_text("old", encoding="utf-8")

    try:
        _select_release_artifacts(dist, "1.0.0rc1")
    except ValueError as exc:
        assert "dist contains non-current YINYO release artifacts" in str(exc)
        assert "yinyo_agent-0.1.0a1-py3-none-any.whl" in str(exc)
    else:
        raise AssertionError("expected stale dist artifact to fail")

    old_wheel.unlink()
    wheel, sdist = _select_release_artifacts(dist, "1.0.0rc1")
    assert wheel == current_wheel
    assert sdist == current_sdist


def test_package_metadata_is_release_ready():
    import os

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pyproject = open(os.path.join(repo, "pyproject.toml"), encoding="utf-8").read()

    assert 'description = "YINYO - a Feishu-native agent with memory, evidence, and release gates"' in pyproject
    assert "闅愭洔" not in pyproject
    assert "鈥" not in pyproject
    assert "— An Autonomous" not in pyproject


def test_release_workflow_accepts_live_smoke_config_and_bundle_inputs():
    import os

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    workflow = open(os.path.join(repo, ".github", "workflows", "release.yml"), encoding="utf-8").read()

    assert "runtime_config_path" in workflow
    assert "smoke_bundle_path" in workflow
    assert "candidate" in workflow
    assert "inputs.runtime_config_path == '' && inputs.smoke_bundle_path == ''" in workflow
    assert "inputs.runtime_config_path != '' && inputs.smoke_bundle_path == ''" in workflow
    assert 'inputs.smoke_bundle_path != \'\'' in workflow
    assert 'inputs.candidate != \'\'' in workflow
    assert '--config "${{ inputs.runtime_config_path }}"' in workflow
    assert '--bundle "${{ inputs.smoke_bundle_path }}"' in workflow
    assert '--candidate "${{ inputs.candidate }}"' in workflow
    assert 'python scripts/verify_release.py --target "${{ inputs.target }}" --bundle "${{ inputs.smoke_bundle_path }}" --json' in workflow
    assert "Verify final release candidate from bundle" in workflow
    assert "Verify final release candidate from runtime config" in workflow
    assert 'python scripts/verify_release.py --target "${{ inputs.target }}" --bundle "${{ inputs.smoke_bundle_path }}" --candidate "${{ inputs.candidate }}" --json' in workflow
    assert 'python scripts/verify_release.py --target "${{ inputs.target }}" --config "${{ inputs.runtime_config_path }}" --candidate "${{ inputs.candidate }}" --json' in workflow
    assert '--config "${{ inputs.runtime_config_path }}" --bundle "${{ inputs.smoke_bundle_path }}" --candidate' not in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "if: always()" in workflow
    assert "release-artifacts/release-audit.json" in workflow
    assert "release-artifacts/candidate-audit.json" in workflow
    assert "dist/*.whl" in workflow
    assert "dist/*.tar.gz" in workflow
    assert "if-no-files-found: error" in workflow


def test_secret_verifier_passes_and_is_wired_to_ci():
    import os
    import subprocess
    import sys

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [sys.executable, "scripts/verify_secrets.py"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    ci = open(os.path.join(repo, ".github", "workflows", "test.yml"), encoding="utf-8").read()
    release = open(os.path.join(repo, ".github", "workflows", "release.yml"), encoding="utf-8").read()

    assert result.returncode == 0
    assert "Secret scan passed" in result.stdout
    assert "python scripts/verify_secrets.py" in ci
    assert "python scripts/verify_secrets.py" in release
    assert "python scripts/replay_scenarios.py --matrix" in ci
    assert "python scripts/replay_scenarios.py --matrix" in release


def test_secret_verifier_scans_config_examples(tmp_path):
    import os
    import subprocess
    import sys

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    (tmp_path / "yinyo.env.example").write_text("deepseek_api_key=REAL_SECRET_VALUE_12345\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "scripts/verify_secrets.py", "--root", str(tmp_path)],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "yinyo.env.example" in result.stdout


def test_gitignore_blocks_local_secret_and_runtime_artifacts():
    import os
    import subprocess

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    paths = [
        "yinyo.env",
        "local.env",
        "workspace/smoke_evidence.jsonl",
        "workspace/runtime.jsonl",
        "workspace/runtime_jobs.jsonl",
        "workspace/gateway_events.jsonl",
        "release-artifacts/release-audit.json",
        "runtime.jsonl",
        "smoke_evidence.jsonl",
    ]

    for path in paths:
        result = subprocess.run(
            ["git", "check-ignore", "--quiet", path],
            cwd=repo,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, path


def test_versioned_env_example_matches_safe_config_template():
    import os
    import subprocess

    from yinyo import RuntimeConfig, build_config_template

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    example_path = os.path.join(repo, "yinyo.env.example")
    text = open(example_path, encoding="utf-8").read()

    assert text == build_config_template(live_smoke=False)
    cfg = RuntimeConfig.load(example_path)
    cfg.validate(require_secrets=False)
    assert cfg.smoke_mode is False
    assert not cfg.app_secret
    assert not cfg.verify_token
    assert not cfg.deepseek_api_key

    result = subprocess.run(
        ["git", "check-ignore", "--quiet", "yinyo.env.example"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1


def test_release_verifier_blocks_1_0_without_live_smoke_evidence():
    import os
    import subprocess
    import sys

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [sys.executable, "scripts/verify_release.py", "--target", "1.0.0"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "R1-03" in result.stdout
    assert "live smoke incomplete" in result.stdout
    assert "smoke_file:" in result.stdout


def test_release_audit_covers_spec_r1_criteria_and_public_docs():
    from yinyo import audit_release_readiness

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = open(os.path.join(repo, "docs", "spec.md"), encoding="utf-8").read()
    spec_ids = re.findall(r"^\| (R1-\d+) \|", spec, flags=re.MULTILINE)

    audit = audit_release_readiness(repo)
    audit_ids = [item["id"] for item in audit["items"]]
    r1_05 = next(item for item in audit["items"] if item["id"] == "R1-05")
    evidence = "\n".join(r1_05["evidence"])

    assert audit_ids == spec_ids
    assert "README.zh-CN.md: yinyo.frontier_readiness.v1" in evidence
    assert "README.md: yinyo.advanced_ref_attestation.v1" in evidence
    assert "README.md: resource quotas" in evidence
    assert "README.md: handoff_ready_records" in evidence
    assert "README.md: replay_handoff()" in evidence
    assert "README.md: live_provenance.ws_sdk_session_id" in evidence
    assert "README.md: ws_sdk_session_id" in evidence
    assert "README.md: feishu_app_id_hash" in evidence
    assert "README.md: sha256(app_id)" in evidence
    assert "README.zh-CN.md: yinyo.advanced_ref_attestation.v1" in evidence
    assert "README.zh-CN.md: resource quotas" in evidence
    assert "README.zh-CN.md: handoff_ready_records" in evidence
    assert "README.zh-CN.md: replay_handoff()" in evidence
    assert "README.zh-CN.md: live_provenance.ws_sdk_session_id" in evidence
    assert "README.zh-CN.md: ws_sdk_session_id" in evidence
    assert "README.zh-CN.md: feishu_app_id_hash" in evidence
    assert "README.zh-CN.md: sha256(app_id)" in evidence
    assert "docs/deployment.md: yinyo.advanced_ref_attestation.v1" in evidence
    assert "docs/deployment.md: yinyo.live_provenance.v1" in evidence
    assert "docs/deployment.md: live_provenance.ws_sdk_session_id" in evidence
    assert "docs/deployment.md: ws_sdk_session_id" in evidence
    assert "docs/deployment.md: feishu_app_id_hash" in evidence
    assert "docs/deployment.md: sha256(app_id)" in evidence
    assert "docs/deployment.md: handoff_ready_records" in evidence
    assert "docs/deployment.md: replay_handoff()" in evidence
    assert "docs/deployment.md: yinyo smoke bundle --config ./yinyo.env --output ./workspace/smoke-bundle --handoff-dir ./workspace/runs" in evidence
    assert "docs/deployment.md: smoke_mode=false" in evidence
    assert "docs/production-checklist.md: yinyo.advanced_ref_attestation.v1" in evidence
    assert "docs/production-checklist.md: yinyo.live_provenance.v1" in evidence
    assert "docs/production-checklist.md: live_provenance.ws_sdk_session_id" in evidence
    assert "docs/production-checklist.md: feishu_app_id_hash" in evidence
    assert "docs/production-checklist.md: sha256(app_id)" in evidence
    assert "docs/production-checklist.md: yinyo.resource_quota.v1" in evidence
    assert "docs/production-checklist.md: README claims trace back to tests, source, or explicit target-state labels" in evidence
    assert "MAINTENANCE.md: python -m yinyo.cli smoke bundle --config ./yinyo.env --output ./workspace/smoke-bundle --handoff-dir ./workspace/runs" in evidence
    assert "MAINTENANCE.md: yinyo.advanced_ref_attestation.v1" in evidence
    assert "MAINTENANCE.md: yinyo.live_provenance.v1" in evidence
    assert "MAINTENANCE.md: live_provenance.ws_sdk_session_id" in evidence
    assert "MAINTENANCE.md: feishu_app_id_hash" in evidence
    assert "MAINTENANCE.md: sha256(app_id)" in evidence
    assert "docs/spec.md: ETCLOVG" in evidence
    assert "docs/spec.md: trace-native proof envelopes" in evidence
    assert "docs/spec.md: yinyo.proof_ablation.v1" in evidence
    assert "docs/roadmap.md: Harness Survey Backlog" in evidence
    assert "docs/roadmap.md: Harden and scale execution environments" in evidence
    assert "docs/roadmap.md: Adaptive simplification" in evidence
    assert r1_05["blockers"] == []


def test_release_verifier_rejects_handwritten_smoke_without_runtime_chain(tmp_path):
    import subprocess
    import sys

    from yinyo import SmokeEvidenceRecorder
    from yinyo.smoke import REQUIRED_1_0_SCENARIOS

    smoke_path = tmp_path / "smoke_evidence.jsonl"
    recorder = SmokeEvidenceRecorder(str(smoke_path))
    for scenario in REQUIRED_1_0_SCENARIOS:
        recorder.record(scenario, "passed", live=True)

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [sys.executable, "scripts/verify_release.py", "--target", "1.0.0", "--smoke-path", str(smoke_path)],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "R1-03" in result.stdout
    assert "runtime_log:text_message_reply" in result.stdout


def test_release_verifier_accepts_gateway_backed_live_smoke_chain(tmp_path, monkeypatch):
    import subprocess
    import sys

    from yinyo import (
        FeishuRuntimeGateway,
        JsonlEventStore,
        JsonlJobQueue,
        RuntimeLogger,
        SmokeEvidenceRecorder,
        verify_smoke_evidence_chain,
    )

    class Session:
        def is_duplicate(self, text, user_id):
            return False

    class Agent:
        session_manager = Session()

        def handle_message(self, user_id, chat_id, text, already_deduped=False, correlation_id=""):
            return {"text": "ok", "files": [{"path": "report.md"}], "run_id": f"run-{correlation_id}"}

    class Adapter:
        agent = Agent()

        def add_reaction(self, message_id):
            return True

        def remove_reaction(self, message_id):
            return True

        def send_message(self, *args, **kwargs):
            return {"success": True, "message_ids": ["om_reply"], "fallback": bool(kwargs.get("files"))}

        def _download_image(self, image_key):
            return image_key

    class VisionAdapter:
        def describe(self, image_path, prompt):
            return {"description": "image description"}

    import yinyo.vision_adapter

    monkeypatch.setattr(yinyo.vision_adapter, "get_vision_adapter", lambda: VisionAdapter())
    smoke_path = tmp_path / "smoke_evidence.jsonl"
    log_path = tmp_path / "runtime.jsonl"
    job_path = tmp_path / "runtime_jobs.jsonl"
    event_path = tmp_path / "gateway_events.jsonl"
    gateway = FeishuRuntimeGateway(
        adapter=Adapter(),
        agent=Adapter.agent,
        verify_token="good-token",
        queue=JsonlJobQueue(str(job_path)),
        event_store=JsonlEventStore(str(event_path)),
        logger=RuntimeLogger(str(log_path)),
        smoke_recorder=SmokeEvidenceRecorder(str(smoke_path)),
    )

    text_event = {
        "type": "event_callback",
        "uuid": "evt_text_chain",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": "hello"}),
                "chat_id": "oc_1",
                "message_id": "om_text_chain",
            },
        },
    }
    image_event = {
        "type": "event_callback",
        "uuid": "evt_image_chain",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "image",
                "content": json.dumps({"image_key": "img_1"}),
                "chat_id": "oc_1",
                "message_id": "om_image_chain",
            },
        },
    }
    gateway.handle_event({"type": "url_verification", "token": "good-token", "challenge": "challenge"}, async_dispatch=False)
    gateway.handle_event(text_event, async_dispatch=False)
    gateway.handle_event(image_event, async_dispatch=False)
    gateway.handle_event(text_event, async_dispatch=False)

    chain = verify_smoke_evidence_chain(
        smoke_path=str(smoke_path),
        log_path=str(log_path),
        job_store_path=str(job_path),
        event_store_path=str(event_path),
    )

    assert chain["ok"] is True
    assert chain["correlation"]["ok"] is True
    assert not chain["correlation"]["missing"]
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [
            sys.executable,
            "scripts/verify_release.py",
            "--target",
            "1.0.0",
            "--workspace",
            str(tmp_path),
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "R1-08" in result.stdout
    assert "missing advanced live scenario" in result.stdout


def test_smoke_chain_rejects_mismatched_correlation_ids(tmp_path):
    from yinyo import JsonlEventStore, JsonlJobQueue, RuntimeLogger, SmokeEvidenceRecorder, verify_smoke_evidence_chain

    smoke = SmokeEvidenceRecorder(str(tmp_path / "smoke_evidence.jsonl"))
    smoke.record("text_message_reply", "passed", live=True, event_key="evt_text_a")
    logger = RuntimeLogger(str(tmp_path / "runtime.jsonl"))
    logger.record("outbox_delivery", correlation_id="evt_text_b", event_key="evt_text_b", success=True)
    queue = JsonlJobQueue(str(tmp_path / "runtime_jobs.jsonl"))
    queue.enqueue("feishu_message", {"event_key": "evt_text_b"}, lambda payload: {"ok": True}, run_async=False)
    event_store = JsonlEventStore(str(tmp_path / "gateway_events.jsonl"))
    event_store.mark_seen("evt_text_b")

    chain = verify_smoke_evidence_chain(
        smoke_path=smoke.path,
        log_path=logger.path,
        job_store_path=queue.path,
        event_store_path=event_store.path,
        required={"text_message_reply"},
    )

    assert chain["ok"] is False
    assert chain["correlation"]["ok"] is False
    assert "correlation:text_message_reply:runtime_log" in chain["missing"]
    assert "correlation:text_message_reply:job_store" in chain["missing"]
    assert "correlation:text_message_reply:event_store" in chain["missing"]


def test_smoke_status_rejects_global_runtime_log_for_wrong_event_key(tmp_path):
    from yinyo import JsonlEventStore, JsonlJobQueue, RuntimeLogger, SmokeEvidenceRecorder, build_smoke_evidence_status

    smoke = SmokeEvidenceRecorder(str(tmp_path / "smoke_evidence.jsonl"))
    smoke.record("text_message_reply", "passed", live=True, event_key="evt_text_a")
    logger = RuntimeLogger(str(tmp_path / "runtime.jsonl"))
    logger.record("outbox_delivery", correlation_id="evt_text_b", event_key="evt_text_b", success=True)
    queue = JsonlJobQueue(str(tmp_path / "runtime_jobs.jsonl"))
    queue.enqueue("feishu_message", {"event_key": "evt_text_b"}, lambda payload: {"ok": True}, run_async=False)
    event_store = JsonlEventStore(str(tmp_path / "gateway_events.jsonl"))
    event_store.mark_seen("evt_text_b")

    status = build_smoke_evidence_status(
        smoke_path=smoke.path,
        log_path=logger.path,
        job_store_path=queue.path,
        event_store_path=event_store.path,
        required={"text_message_reply"},
    )
    text_status = next(item for item in status["scenarios"] if item["scenario"] == "text_message_reply")

    assert status["ok"] is False
    assert text_status["ok"] is False
    assert "runtime_log" in text_status["missing"]
    assert "outbox_delivery" in text_status["missing"]
    assert text_status["runtime_events_seen"] == []
    assert any(
        item["layer"] == "basic"
        and item["scenario"] == "text_message_reply"
        and "runtime_log" in item["missing"]
        for item in status["operator_plan"]
    )


def test_smoke_status_reports_per_event_job_and_event_store_gaps(tmp_path):
    from yinyo import JsonlEventStore, JsonlJobQueue, RuntimeLogger, SmokeEvidenceRecorder, build_smoke_evidence_status

    smoke = SmokeEvidenceRecorder(str(tmp_path / "smoke_evidence.jsonl"))
    smoke.record("text_message_reply", "passed", live=True, event_key="evt_expected")
    logger = RuntimeLogger(str(tmp_path / "runtime.jsonl"))
    logger.record("outbox_delivery", correlation_id="evt_expected", event_key="evt_expected", success=True)
    queue = JsonlJobQueue(str(tmp_path / "runtime_jobs.jsonl"))
    queue.enqueue("feishu_message", {"event_key": "evt_other"}, lambda payload: {"ok": True}, run_async=False)
    event_store = JsonlEventStore(str(tmp_path / "gateway_events.jsonl"))
    event_store.mark_seen("evt_other")

    status = build_smoke_evidence_status(
        smoke_path=smoke.path,
        log_path=logger.path,
        job_store_path=queue.path,
        event_store_path=event_store.path,
        required={"text_message_reply"},
    )
    text_status = next(item for item in status["scenarios"] if item["scenario"] == "text_message_reply")

    assert status["ok"] is False
    assert "correlation:text_message_reply:job_store" in status["chain"]["missing"]
    assert "correlation:text_message_reply:event_store" in status["chain"]["missing"]
    assert text_status["ok"] is False
    assert "job_store" in text_status["missing"]
    assert "event_store" in text_status["missing"]
    assert "runtime_log" not in text_status["missing"]
    assert "outbox_delivery" not in text_status["missing"]
    assert any(
        item["layer"] == "basic"
        and item["scenario"] == "text_message_reply"
        and "job_store" in item["missing"]
        and "event_store" in item["missing"]
        for item in status["operator_plan"]
    )


def test_smoke_chain_rejects_failed_job_for_matching_event_key(tmp_path):
    from yinyo import JsonlEventStore, JsonlJobQueue, RuntimeLogger, SmokeEvidenceRecorder, build_smoke_evidence_status, verify_smoke_evidence_chain

    smoke = SmokeEvidenceRecorder(str(tmp_path / "smoke_evidence.jsonl"))
    smoke.record("text_message_reply", "passed", live=True, event_key="evt_text_failed")
    logger = RuntimeLogger(str(tmp_path / "runtime.jsonl"))
    logger.record("outbox_delivery", correlation_id="evt_text_failed", event_key="evt_text_failed", success=True)
    event_store = JsonlEventStore(str(tmp_path / "gateway_events.jsonl"))
    event_store.mark_seen("evt_text_failed")
    queue = JsonlJobQueue(str(tmp_path / "runtime_jobs.jsonl"))
    queue.enqueue("feishu_message", {"event_key": "evt_text_failed"}, lambda payload: (_ for _ in ()).throw(RuntimeError("boom")), run_async=False)
    queue.enqueue("feishu_message", {"event_key": "evt_other"}, lambda payload: {"ok": True}, run_async=False)

    chain = verify_smoke_evidence_chain(
        smoke_path=smoke.path,
        log_path=logger.path,
        job_store_path=queue.path,
        event_store_path=event_store.path,
        required={"text_message_reply"},
    )
    status = build_smoke_evidence_status(
        smoke_path=smoke.path,
        log_path=logger.path,
        job_store_path=queue.path,
        event_store_path=event_store.path,
        required={"text_message_reply"},
    )
    text_status = next(item for item in status["scenarios"] if item["scenario"] == "text_message_reply")

    assert chain["ok"] is False
    assert "job_store:text_message_reply:status" in chain["missing"]
    assert "correlation:text_message_reply:job_store" in chain["missing"]
    assert chain["correlation"]["chains"][0]["job_status"] == "failed"
    assert status["ok"] is False
    assert text_status["job_status"] == "failed"
    assert "job_store_status" in text_status["missing"]
    assert any(
        item["layer"] == "basic"
        and item["scenario"] == "text_message_reply"
        and "job_store_status" in item["missing"]
        for item in status["operator_plan"]
    )


def test_smoke_status_rejects_stale_records_before_latest_service_start(tmp_path):
    from yinyo import JsonlEventStore, JsonlJobQueue, RuntimeLogger, SmokeEvidenceRecorder, build_smoke_evidence_status

    smoke = SmokeEvidenceRecorder(str(tmp_path / "smoke_evidence.jsonl"))
    logger = RuntimeLogger(str(tmp_path / "runtime.jsonl"))
    event_store = JsonlEventStore(str(tmp_path / "gateway_events.jsonl"))
    queue = JsonlJobQueue(str(tmp_path / "runtime_jobs.jsonl"))
    smoke.record("text_message_reply", "passed", live=True, event_key="evt_old")
    logger.record("outbox_delivery", correlation_id="evt_old", event_key="evt_old", success=True)
    queue.enqueue("feishu_message", {"event_key": "evt_old"}, lambda payload: {"ok": True}, run_async=False)
    event_store.mark_seen("evt_old")
    logger.record("service_start", correlation_id="service", transport="ws", profile="local")

    status = build_smoke_evidence_status(
        smoke_path=smoke.path,
        log_path=logger.path,
        job_store_path=queue.path,
        event_store_path=event_store.path,
        transport="http",
        required={"text_message_reply"},
    )
    text_status = next(item for item in status["scenarios"] if item["scenario"] == "text_message_reply")

    assert status["ok"] is False
    assert status["session"]["ok"] is False
    assert status["session"]["stale_scenarios"] == ["text_message_reply"]
    assert "smoke_session:stale:text_message_reply" in status["chain"]["missing"]
    assert "stale_session" in text_status["missing"]
    assert any("smoke reset" in item for item in status["next_actions"])


def test_card_fallback_probe_before_final_restart_is_allowed(tmp_path):
    from yinyo import JsonlEventStore, JsonlJobQueue, RuntimeLogger, SmokeEvidenceRecorder, build_smoke_evidence_status

    smoke = SmokeEvidenceRecorder(str(tmp_path / "smoke_evidence.jsonl"))
    logger = RuntimeLogger(str(tmp_path / "runtime.jsonl"))
    event_store = JsonlEventStore(str(tmp_path / "gateway_events.jsonl"))
    queue = JsonlJobQueue(str(tmp_path / "runtime_jobs.jsonl"))
    logger.record("service_start", correlation_id="service", transport="ws", profile="local", smoke_mode=True)
    smoke.record("card_fallback", "passed", live=True, event_key="evt_card_probe")
    logger.record(
        "outbox_delivery",
        correlation_id="evt_card_probe",
        event_key="evt_card_probe",
        success=True,
        fallback=True,
    )
    logger.record(
        "ws_event_received",
        correlation_id="evt_card_probe",
        event_key="evt_card_probe",
        ack_latency_ms=12.5,
        ack_deadline_ms=3000.0,
        ack_within_deadline=True,
    )
    queue.enqueue("feishu_message", {"event_key": "evt_card_probe"}, lambda payload: {"ok": True}, run_async=False)
    event_store.mark_seen("evt_card_probe")
    logger.record("service_start", correlation_id="service", transport="ws", profile="local", smoke_mode=False)

    status = build_smoke_evidence_status(
        smoke_path=smoke.path,
        log_path=logger.path,
        job_store_path=queue.path,
        event_store_path=event_store.path,
        transport="ws",
        required={"card_fallback"},
    )
    card_status = next(item for item in status["scenarios"] if item["scenario"] == "card_fallback")

    assert status["chain"]["session"]["ok"] is True
    assert status["session"]["allowed_probe_scenarios"] == ["card_fallback"]
    assert status["session"]["stale_scenarios"] == []
    assert "smoke_session:stale:card_fallback" not in status["chain"]["missing"]
    assert "stale_session" not in card_status["missing"]


def test_smoke_session_allows_only_immediately_preceding_card_probe(tmp_path):
    from yinyo import JsonlEventStore, JsonlJobQueue, RuntimeLogger, SmokeEvidenceRecorder, build_smoke_evidence_status

    smoke = SmokeEvidenceRecorder(str(tmp_path / "smoke_evidence.jsonl"))
    logger = RuntimeLogger(str(tmp_path / "runtime.jsonl"))
    event_store = JsonlEventStore(str(tmp_path / "gateway_events.jsonl"))
    queue = JsonlJobQueue(str(tmp_path / "runtime_jobs.jsonl"))
    logger.record("service_start", correlation_id="service", transport="ws", profile="local", smoke_mode=True)
    smoke.record("card_fallback", "passed", live=True, event_key="evt_old_card_probe")
    logger.record(
        "outbox_delivery",
        correlation_id="evt_old_card_probe",
        event_key="evt_old_card_probe",
        success=True,
        fallback=True,
    )
    logger.record(
        "ws_event_received",
        correlation_id="evt_old_card_probe",
        event_key="evt_old_card_probe",
        ack_latency_ms=12.5,
        ack_deadline_ms=3000.0,
        ack_within_deadline=True,
    )
    queue.enqueue("feishu_message", {"event_key": "evt_old_card_probe"}, lambda payload: {"ok": True}, run_async=False)
    event_store.mark_seen("evt_old_card_probe")
    logger.record("service_start", correlation_id="service", transport="ws", profile="local", smoke_mode=False)
    logger.record("service_start", correlation_id="service", transport="ws", profile="local", smoke_mode=False)

    status = build_smoke_evidence_status(
        smoke_path=smoke.path,
        log_path=logger.path,
        job_store_path=queue.path,
        event_store_path=event_store.path,
        transport="ws",
        required={"card_fallback"},
    )

    assert status["ok"] is False
    assert status["session"]["allowed_probe_scenarios"] == []
    assert status["session"]["stale_scenarios"] == ["card_fallback"]
    assert "smoke_session:stale:card_fallback" in status["chain"]["missing"]


def test_smoke_chain_rejects_duplicate_without_original_job(tmp_path):
    from yinyo import JsonlEventStore, JsonlJobQueue, RuntimeLogger, SmokeEvidenceRecorder, verify_smoke_evidence_chain

    smoke = SmokeEvidenceRecorder(str(tmp_path / "smoke_evidence.jsonl"))
    smoke.record("duplicate_callback", "passed", live=True, event_key="evt_dup")
    logger = RuntimeLogger(str(tmp_path / "runtime.jsonl"))
    logger.record("webhook_duplicate", correlation_id="evt_dup", event_key="evt_dup")
    event_store = JsonlEventStore(str(tmp_path / "gateway_events.jsonl"))
    event_store.mark_seen("evt_dup")
    queue = JsonlJobQueue(str(tmp_path / "runtime_jobs.jsonl"))

    chain = verify_smoke_evidence_chain(
        smoke_path=smoke.path,
        log_path=logger.path,
        job_store_path=queue.path,
        event_store_path=event_store.path,
        required={"duplicate_callback"},
    )

    assert chain["ok"] is False
    assert "correlation:duplicate_callback:job_store" in chain["missing"]


def test_release_verifier_uses_runtime_config_for_live_smoke_chain(tmp_path, monkeypatch):
    import subprocess
    import sys

    from yinyo import (
        FeishuRuntimeGateway,
        JsonlEventStore,
        JsonlJobQueue,
        RuntimeLogger,
        SmokeEvidenceRecorder,
    )

    class Session:
        def is_duplicate(self, text, user_id):
            return False

    class Agent:
        session_manager = Session()

        def handle_message(self, user_id, chat_id, text, already_deduped=False, correlation_id=""):
            return {"text": "ok", "files": [{"path": "report.md"}], "run_id": f"run-{correlation_id}"}

    class Adapter:
        agent = Agent()

        def add_reaction(self, message_id):
            return True

        def remove_reaction(self, message_id):
            return True

        def send_message(self, *args, **kwargs):
            return {"success": True, "message_ids": ["om_reply"], "fallback": bool(kwargs.get("files"))}

        def _download_image(self, image_key):
            return image_key

    class VisionAdapter:
        def describe(self, image_path, prompt):
            return {"description": "image description"}

    import yinyo.vision_adapter

    monkeypatch.setattr(yinyo.vision_adapter, "get_vision_adapter", lambda: VisionAdapter())
    evidence_dir = tmp_path / "live-evidence"
    smoke_path = evidence_dir / "custom-smoke.jsonl"
    log_path = evidence_dir / "custom-runtime.jsonl"
    job_path = evidence_dir / "custom-jobs.jsonl"
    event_path = evidence_dir / "custom-events.jsonl"
    gateway = FeishuRuntimeGateway(
        adapter=Adapter(),
        agent=Adapter.agent,
        verify_token="good-token",
        queue=JsonlJobQueue(str(job_path)),
        event_store=JsonlEventStore(str(event_path)),
        logger=RuntimeLogger(str(log_path)),
        smoke_recorder=SmokeEvidenceRecorder(str(smoke_path)),
    )
    text_event = {
        "type": "event_callback",
        "uuid": "evt_text_config",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": "hello"}),
                "chat_id": "oc_1",
                "message_id": "om_text_config",
            },
        },
    }
    image_event = {
        "type": "event_callback",
        "uuid": "evt_image_config",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "image",
                "content": json.dumps({"image_key": "img_1"}),
                "chat_id": "oc_1",
                "message_id": "om_image_config",
            },
        },
    }
    gateway.handle_event(text_event, async_dispatch=False)
    gateway.handle_event(image_event, async_dispatch=False)
    gateway.handle_event(text_event, async_dispatch=False)
    _record_advanced_live_evidence(gateway.smoke_recorder)

    config_path = tmp_path / "yinyo.env"
    config_path.write_text(
        "\n".join([
            f"workspace={tmp_path / 'unused-default-workspace'}",
            f"smoke_evidence_path={smoke_path}",
            f"log_path={log_path}",
            f"job_store_path={job_path}",
            f"event_store_path={event_path}",
        ]),
        encoding="utf-8",
    )
    _record_ws_runtime_evidence(
        gateway.logger,
        event_keys=_smoke_event_keys(gateway),
        ws_sdk_session_id="session-live-001",
    )

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [
            sys.executable,
            "scripts/verify_release.py",
            "--target",
            "1.0.0",
            "--config",
            str(config_path),
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Release verification passed" in result.stdout


def test_smoke_evidence_status_reports_gateway_backed_chain(tmp_path, monkeypatch):
    from yinyo import (
        FeishuRuntimeGateway,
        JsonlEventStore,
        JsonlJobQueue,
        RuntimeLogger,
        SmokeEvidenceRecorder,
        build_smoke_evidence_status,
    )

    class Session:
        def is_duplicate(self, text, user_id):
            return False

    class Agent:
        session_manager = Session()

        def handle_message(self, user_id, chat_id, text, already_deduped=False, correlation_id=""):
            return {"text": "ok", "files": [{"path": "report.md"}], "run_id": f"run-{correlation_id}"}

    class Adapter:
        agent = Agent()

        def add_reaction(self, message_id):
            return True

        def remove_reaction(self, message_id):
            return True

        def send_message(self, *args, **kwargs):
            return {"success": True, "message_ids": ["om_reply"], "fallback": bool(kwargs.get("files"))}

        def _download_image(self, image_key):
            return image_key

    class VisionAdapter:
        def describe(self, image_path, prompt):
            return {"description": "image description"}

    import yinyo.vision_adapter

    monkeypatch.setattr(yinyo.vision_adapter, "get_vision_adapter", lambda: VisionAdapter())
    smoke_path = tmp_path / "smoke_evidence.jsonl"
    log_path = tmp_path / "runtime.jsonl"
    job_path = tmp_path / "runtime_jobs.jsonl"
    event_path = tmp_path / "gateway_events.jsonl"
    gateway = FeishuRuntimeGateway(
        adapter=Adapter(),
        agent=Adapter.agent,
        verify_token="good-token",
        queue=JsonlJobQueue(str(job_path)),
        event_store=JsonlEventStore(str(event_path)),
        logger=RuntimeLogger(str(log_path)),
        smoke_recorder=SmokeEvidenceRecorder(str(smoke_path)),
    )

    text_event = {
        "type": "event_callback",
        "uuid": "evt_text_status",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": "hello"}),
                "chat_id": "oc_1",
                "message_id": "om_text_status",
            },
        },
    }
    image_event = {
        "type": "event_callback",
        "uuid": "evt_image_status",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "image",
                "content": json.dumps({"image_key": "img_1"}),
                "chat_id": "oc_1",
                "message_id": "om_image_status",
            },
        },
    }
    gateway.handle_event({"type": "url_verification", "token": "good-token", "challenge": "challenge"}, async_dispatch=False)
    gateway.handle_event(text_event, async_dispatch=False)
    gateway.handle_event(image_event, async_dispatch=False)
    gateway.handle_event(text_event, async_dispatch=False)
    _record_advanced_live_evidence(gateway.smoke_recorder)

    status = build_smoke_evidence_status(
        smoke_path=str(smoke_path),
        log_path=str(log_path),
        job_store_path=str(job_path),
        event_store_path=str(event_path),
    )

    assert status["ok"] is True
    assert status["next_actions"] == []
    assert status["job_store"]["feishu_message_succeeded"] is True
    assert all(item["ok"] for item in status["scenarios"])
    assert all(item["ok"] for item in status["advanced_scenarios"])
    assert status["advanced"]["ok"] is True


def test_smoke_evidence_status_requires_advanced_live_records(tmp_path, monkeypatch):
    from yinyo import (
        FeishuRuntimeGateway,
        JsonlEventStore,
        JsonlJobQueue,
        RuntimeLogger,
        SmokeEvidenceRecorder,
        build_smoke_evidence_status,
    )

    class Session:
        def is_duplicate(self, text, user_id):
            return False

    class Agent:
        session_manager = Session()

        def handle_message(self, user_id, chat_id, text, already_deduped=False, correlation_id=""):
            return {"text": "ok", "files": [{"path": "report.md"}], "run_id": f"run-{correlation_id}"}

    class Adapter:
        agent = Agent()

        def add_reaction(self, message_id):
            return True

        def remove_reaction(self, message_id):
            return True

        def send_message(self, *args, **kwargs):
            return {"success": True, "message_ids": ["om_reply"], "fallback": bool(kwargs.get("files"))}

        def _download_image(self, image_key):
            return image_key

    class VisionAdapter:
        def describe(self, image_path, prompt):
            return {"description": "image description"}

    import yinyo.vision_adapter

    monkeypatch.setattr(yinyo.vision_adapter, "get_vision_adapter", lambda: VisionAdapter())
    smoke_path = tmp_path / "smoke_evidence.jsonl"
    log_path = tmp_path / "runtime.jsonl"
    job_path = tmp_path / "runtime_jobs.jsonl"
    event_path = tmp_path / "gateway_events.jsonl"
    gateway = FeishuRuntimeGateway(
        adapter=Adapter(),
        agent=Adapter.agent,
        verify_token="good-token",
        queue=JsonlJobQueue(str(job_path)),
        event_store=JsonlEventStore(str(event_path)),
        logger=RuntimeLogger(str(log_path)),
        smoke_recorder=SmokeEvidenceRecorder(str(smoke_path)),
    )
    text_event = {
        "type": "event_callback",
        "uuid": "evt_text_status_missing_advanced",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": "hello"}),
                "chat_id": "oc_1",
                "message_id": "om_text_status_missing_advanced",
            },
        },
    }
    image_event = {
        "type": "event_callback",
        "uuid": "evt_image_status_missing_advanced",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "image",
                "content": json.dumps({"image_key": "img_1"}),
                "chat_id": "oc_1",
                "message_id": "om_image_status_missing_advanced",
            },
        },
    }
    gateway.handle_event({"type": "url_verification", "token": "good-token", "challenge": "challenge"}, async_dispatch=False)
    gateway.handle_event(text_event, async_dispatch=False)
    gateway.handle_event(image_event, async_dispatch=False)
    gateway.handle_event(text_event, async_dispatch=False)

    status = build_smoke_evidence_status(
        smoke_path=str(smoke_path),
        log_path=str(log_path),
        job_store_path=str(job_path),
        event_store_path=str(event_path),
    )

    assert status["ok"] is False
    assert status["chain"]["chain_ok"] is True
    assert status["chain"]["advanced_ok"] is False
    assert status["advanced"]["missing"] == [
        "deepseek_usage",
        "image_understanding",
        "long_conversation",
        "memory_supersession",
        "partial_failure",
        "trace2skill_promotion",
    ]
    assert any("advanced:" in item for item in status["chain"]["missing"])
    assert any(item["scenario"] == "trace2skill_promotion" and not item["ok"] for item in status["advanced_scenarios"])


def test_release_verifier_json_reports_r1_readiness(tmp_path):
    import os
    import subprocess
    import sys

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [sys.executable, "scripts/verify_release.py", "--target", "1.0.0", "--json"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    data = json.loads(result.stdout)
    items = {item["id"]: item for item in data["items"]}

    assert result.returncode == 1
    assert data["ok"] is False
    assert data["corpus_contract_ok"] is True
    assert data["corpus_contract_errors"] == []
    assert len(data["corpus_sha256"]) == 64
    assert data["live_matrix_ok"] is False
    assert data["live_matrix"]["schema"] == "yinyo.live_release_matrix.v1"
    assert "ws_ack_boundary" in data["live_matrix"]["missing_scenarios"]
    reliability = next(row for row in data["live_matrix"]["rows"] if row["id"] == "trait.reliability")
    assert "ws_ack_boundary" in reliability["live_missing"]
    assert items["R1-01"]["passed"] is True
    assert items["R1-08"]["passed"] is False
    assert "image_understanding" in items["R1-08"]["evidence"]
    assert "image_reply" not in items["R1-08"]["evidence"]
    assert items["R1-11"]["passed"] is False
    assert any("missing advanced live" in blocker for blocker in items["R1-11"]["blockers"])
    assert items["R1-03"]["passed"] is False
    assert any("smoke_file:" in blocker for blocker in items["R1-03"]["blockers"])


def test_live_release_matrix_accepts_verified_ws_bundle_override():
    from yinyo.release_matrix import evaluate_live_release_matrix

    advanced_scenarios = [
        "deepseek_usage",
        "image_understanding",
        "long_conversation",
        "memory_supersession",
        "partial_failure",
        "trace2skill_promotion",
    ]
    manifest = {
        "runtime": {"transport": "ws"},
        "chain": {
            "smoke": {
                "passed": [
                    "text_message_reply",
                    "image_message_reply",
                    "card_fallback",
                    "duplicate_callback",
                ],
            },
            "correlation": {
                "chains": [
                    {"scenario": "text_message_reply", "ok": True},
                ],
            },
        },
        "advanced": {
            "passed": advanced_scenarios,
        },
        "advanced_ref_attestation": {
            "schema": "yinyo.advanced_ref_attestation.v1",
            "ok": True,
            "digest": "a" * 64,
            "scenarios": {
                scenario: {
                    "schema": "yinyo.advanced_ref_attestation.scenario.v1",
                    "scenario": scenario,
                    "ok": True,
                    "ref_resolution_schema": "yinyo.advanced_ref_resolution.v1",
                    "ref_resolution_mode": "local",
                    "unresolved": [],
                    "proof_schema": "yinyo.advanced_live_proof.v1",
                    "proof_digest": "b" * 64,
                }
                for scenario in advanced_scenarios
            },
        },
    }

    result = evaluate_live_release_matrix(bundle={"ok": True, "manifest": manifest})

    assert result["ok"] is True
    assert result["bundle_verified"] is True
    assert result["missing_scenarios"] == []
    assert "verified_ws_bundle" in result["passed_scenarios"]
    assert "ws_ack_boundary" in result["passed_scenarios"]


def test_live_release_matrix_rejects_bundle_advanced_without_attestation():
    from yinyo.release_matrix import evaluate_live_release_matrix

    manifest = {
        "runtime": {"transport": "ws"},
        "chain": {
            "smoke": {
                "passed": [
                    "text_message_reply",
                    "image_message_reply",
                    "card_fallback",
                    "duplicate_callback",
                ],
            },
            "correlation": {"chains": [{"scenario": "text_message_reply", "ok": True}]},
        },
        "advanced": {
            "passed": [
                "deepseek_usage",
                "image_understanding",
                "long_conversation",
                "memory_supersession",
                "partial_failure",
                "trace2skill_promotion",
            ],
        },
    }

    result = evaluate_live_release_matrix(bundle={"ok": True, "manifest": manifest})

    assert result["ok"] is False
    assert result["bundle_verified"] is True
    assert "verified_ws_bundle" in result["passed_scenarios"]
    assert "ws_ack_boundary" in result["passed_scenarios"]
    assert "deepseek_usage" in result["missing_scenarios"]
    assert "trace2skill_promotion" in result["missing_scenarios"]


def test_release_readiness_uses_live_matrix_missing_scenarios_for_bundle_override(tmp_path):
    from yinyo.readiness import audit_release_readiness

    manifest = {
        "runtime": {"transport": "ws"},
        "handoffs": {"records": 1, "ready_records": 1},
        "chain": {
            "smoke": {
                "passed": [
                    "text_message_reply",
                    "image_message_reply",
                    "card_fallback",
                    "duplicate_callback",
                ],
            },
            "correlation": {"chains": [{"scenario": "text_message_reply", "ok": True}]},
        },
        "advanced": {
            "passed": [
                "deepseek_usage",
                "image_understanding",
                "long_conversation",
                "memory_supersession",
                "partial_failure",
                "trace2skill_promotion",
            ],
        },
    }

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = audit_release_readiness(
        repo,
        target="1.0.0",
        live_smoke_override={
            "path": str(tmp_path / "bundle"),
            "ok": True,
            "transport": "ws",
            "handoff_records": 1,
            "handoff_ready_records": 1,
            "manifest": manifest,
        },
    )
    items = {item["id"]: item for item in result["items"]}

    assert result["live_matrix_ok"] is False
    assert items["R1-07"]["passed"] is True
    assert items["R1-08"]["passed"] is False
    assert "live matrix missing scenario: image_understanding" in items["R1-08"]["blockers"]
    assert items["R1-09"]["passed"] is False
    assert "live matrix missing scenario: trace2skill_promotion" in items["R1-09"]["blockers"]
    assert items["R1-10"]["passed"] is False
    assert "live matrix missing scenario: deepseek_usage" in items["R1-10"]["blockers"]
    assert items["R1-11"]["passed"] is False
    assert "live matrix missing scenario: verified_ws_bundle" not in items["R1-11"]["blockers"]


def test_live_release_matrix_rejects_ws_ack_without_correlation_chain():
    from yinyo.release_matrix import evaluate_live_release_matrix

    advanced_scenarios = [
        "deepseek_usage",
        "image_understanding",
        "long_conversation",
        "memory_supersession",
        "partial_failure",
        "trace2skill_promotion",
    ]
    manifest = {
        "runtime": {"transport": "ws"},
        "chain": {
            "smoke": {
                "passed": [
                    "text_message_reply",
                    "image_message_reply",
                    "card_fallback",
                    "duplicate_callback",
                ],
            },
            "correlation": {"chains": []},
        },
        "advanced": {"passed": advanced_scenarios},
        "advanced_ref_attestation": {
            "schema": "yinyo.advanced_ref_attestation.v1",
            "ok": True,
            "digest": "a" * 64,
            "scenarios": {
                scenario: {
                    "schema": "yinyo.advanced_ref_attestation.scenario.v1",
                    "scenario": scenario,
                    "ok": True,
                    "ref_resolution_schema": "yinyo.advanced_ref_resolution.v1",
                    "ref_resolution_mode": "local",
                    "unresolved": [],
                    "proof_schema": "yinyo.advanced_live_proof.v1",
                    "proof_digest": "b" * 64,
                }
                for scenario in advanced_scenarios
            },
        },
    }

    result = evaluate_live_release_matrix(bundle={"ok": True, "manifest": manifest})

    assert result["ok"] is False
    assert "ws_ack_boundary" in result["missing_scenarios"]
    assert "ws_ack_boundary" not in result["passed_scenarios"]
    assert "deepseek_usage" in result["passed_scenarios"]


def test_release_candidate_1_0_requires_target_and_live_evidence():
    import os
    import subprocess
    import sys

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [sys.executable, "scripts/verify_release.py", "--candidate", "1.0.0", "--json"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    data = json.loads(result.stdout)

    assert result.returncode == 1
    assert data["candidate"]["ok"] is False
    assert "candidate 1.0.0 requires --target 1.0.0" in data["candidate"]["blockers"]
    assert any("verified live smoke evidence" in item for item in data["candidate"]["blockers"])


def test_cli_smoke_bundle_writes_redacted_release_evidence(tmp_path, monkeypatch):
    import subprocess
    import sys

    from yinyo import FeishuRuntimeGateway, JsonlEventStore, JsonlJobQueue, RuntimeLogger, SmokeEvidenceRecorder

    class Session:
        def is_duplicate(self, text, user_id):
            return False

    class Agent:
        session_manager = Session()

        def handle_message(self, user_id, chat_id, text, already_deduped=False, correlation_id=""):
            return {"text": "ok", "files": [{"path": "report.md"}], "run_id": f"run-{correlation_id}"}

    class Adapter:
        agent = Agent()

        def add_reaction(self, message_id):
            return True

        def remove_reaction(self, message_id):
            return True

        def send_message(self, *args, **kwargs):
            return {"success": True, "message_ids": ["om_reply"], "fallback": bool(kwargs.get("files"))}

        def _download_image(self, image_key):
            return image_key

    class VisionAdapter:
        def describe(self, image_path, prompt):
            return {"description": "image description"}

    import yinyo.vision_adapter

    monkeypatch.setattr(yinyo.vision_adapter, "get_vision_adapter", lambda: VisionAdapter())
    gateway = FeishuRuntimeGateway(
        adapter=Adapter(),
        agent=Adapter.agent,
        verify_token="good-token",
        queue=JsonlJobQueue(str(tmp_path / "runtime_jobs.jsonl")),
        event_store=JsonlEventStore(str(tmp_path / "gateway_events.jsonl")),
        logger=RuntimeLogger(str(tmp_path / "runtime.jsonl")),
        smoke_recorder=SmokeEvidenceRecorder(str(tmp_path / "smoke_evidence.jsonl")),
    )
    text_event = {
        "type": "event_callback",
        "uuid": "evt_bundle_text",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": "hello"}),
                "chat_id": "oc_1",
                "message_id": "om_bundle_text",
            },
        },
    }
    image_event = {
        "type": "event_callback",
        "uuid": "evt_bundle_image",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "image",
                "content": json.dumps({"image_key": "img_1"}),
                "chat_id": "oc_1",
                "message_id": "om_bundle_image",
            },
        },
    }
    gateway.handle_event({"type": "url_verification", "token": "good-token", "challenge": "challenge"}, async_dispatch=False)
    gateway.handle_event(text_event, async_dispatch=False)
    gateway.handle_event(image_event, async_dispatch=False)
    gateway.handle_event(text_event, async_dispatch=False)
    _record_advanced_live_evidence(gateway.smoke_recorder)
    _write_replayable_handoff(tmp_path / "runs" / "run-handoff", run_id="run-handoff", correlation_id="evt_bundle_text")
    (tmp_path / "runtime.jsonl").write_text(
        (tmp_path / "runtime.jsonl").read_text(encoding="utf-8")
        + '{"event":"debug","correlation_id":"evt_secret","token":"sk-secret-value"}\n',
        encoding="utf-8",
    )

    config_path = tmp_path / "runtime.env"
    config_path.write_text(
        "\n".join([
            f"workspace={tmp_path}",
            "transport=http",
            "app_id=app",
            "app_secret=super-secret",
            "verify_token=verify-secret",
            "deepseek_api_key=sk-secret",
        ]),
        encoding="utf-8",
    )
    output_dir = tmp_path / "bundle"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "smoke",
            "bundle",
            "--config",
            str(config_path),
            "--output",
            str(output_dir),
            "--handoff-dir",
            str(tmp_path / "runs"),
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    data = json.loads(result.stdout)

    assert result.returncode == 0
    assert data["ok"] is True
    assert (output_dir / "manifest.json").is_file()
    assert (output_dir / "chain.json").is_file()
    assert (output_dir / "advanced.json").is_file()
    assert (output_dir / "diagnostics.json").is_file()
    assert (output_dir / "runtime.redacted.jsonl").is_file()
    assert (output_dir / "handoffs" / "run-handoff.handoff.json").is_file()
    assert data["handoffs"]["records"] == 1
    assert data["handoffs"]["ready_records"] == 1
    assert data["handoffs"]["files"][0]["replay_ok"] is True
    assert "handoff:run-handoff" in data["file_hashes"]
    assert data["frontier_readiness"]["schema"] == "yinyo.frontier_readiness.v1"
    assert data["frontier_readiness"]["local_matrix_ok"] is True
    assert data["frontier_readiness"]["bundle_verified"] is True
    assert data["frontier_readiness"]["handoff_records"] == 1
    assert data["frontier_readiness"]["handoff_ready_records"] == 1
    assert data["frontier_readiness"]["handoff_required"] is False
    assert data["frontier_readiness"]["ok"] is True
    assert "sk-secret-value" not in (output_dir / "runtime.redacted.jsonl").read_text(encoding="utf-8")
    assert "super-secret" not in result.stdout
    assert "verify-secret" not in result.stdout
    assert "sk-secret" not in result.stdout


def test_cli_smoke_bundle_reports_advanced_missing_in_text_output(tmp_path):
    import subprocess
    import sys

    config_path = tmp_path / "runtime.env"
    config_path.write_text(f"workspace={tmp_path}\n", encoding="utf-8")
    output_dir = tmp_path / "bundle"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "smoke",
            "bundle",
            "--config",
            str(config_path),
            "--output",
            str(output_dir),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "YINYO smoke evidence bundle: ATTENTION" in result.stdout
    assert "chain_missing:" in result.stdout
    assert "advanced_missing:" in result.stdout
    assert "advanced_field_missing:" in result.stdout
    assert "diagnostics_alerts:" in result.stdout
    assert "operator_next_actions:" in result.stdout
    assert "operator_plan:" in result.stdout
    assert "image_understanding" in result.stdout
    assert "Run a real Feishu image workflow" in result.stdout


def test_cli_smoke_bundle_handoff_warning_uses_config_workspace(tmp_path):
    import subprocess
    import sys

    workspace = tmp_path / "custom-workspace"
    config_path = tmp_path / "runtime.env"
    config_path.write_text(f"workspace={workspace}\ntransport=ws\n", encoding="utf-8")
    output_dir = tmp_path / "bundle"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "smoke",
            "bundle",
            "--config",
            str(config_path),
            "--output",
            str(output_dir),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    expected = f"rerun with --handoff-dir {workspace / 'runs'}"
    assert expected in result.stdout
    assert "rerun with --handoff-dir ./workspace/runs" not in result.stdout


def test_release_verifier_accepts_redacted_smoke_bundle(tmp_path, monkeypatch):
    import subprocess
    import sys

    from yinyo import FeishuRuntimeGateway, JsonlEventStore, JsonlJobQueue, RuntimeLogger, SmokeEvidenceRecorder

    class Session:
        def is_duplicate(self, text, user_id):
            return False

    class Agent:
        session_manager = Session()

        def handle_message(self, user_id, chat_id, text, already_deduped=False, correlation_id=""):
            return {"text": "ok", "files": [{"path": "report.md"}], "run_id": f"run-{correlation_id}"}

    class Adapter:
        agent = Agent()

        def add_reaction(self, message_id):
            return True

        def remove_reaction(self, message_id):
            return True

        def send_message(self, *args, **kwargs):
            return {"success": True, "message_ids": ["om_reply"], "fallback": bool(kwargs.get("files"))}

        def _download_image(self, image_key):
            return image_key

    class VisionAdapter:
        def describe(self, image_path, prompt):
            return {"description": "image description"}

    import yinyo.vision_adapter

    monkeypatch.setattr(yinyo.vision_adapter, "get_vision_adapter", lambda: VisionAdapter())
    gateway = FeishuRuntimeGateway(
        adapter=Adapter(),
        agent=Adapter.agent,
        verify_token="good-token",
        queue=JsonlJobQueue(str(tmp_path / "runtime_jobs.jsonl")),
        event_store=JsonlEventStore(str(tmp_path / "gateway_events.jsonl")),
        logger=RuntimeLogger(str(tmp_path / "runtime.jsonl")),
        smoke_recorder=SmokeEvidenceRecorder(str(tmp_path / "smoke_evidence.jsonl")),
    )
    text_event = {
        "type": "event_callback",
        "uuid": "evt_bundle_verify_text",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": "hello"}),
                "chat_id": "oc_1",
                "message_id": "om_bundle_verify_text",
            },
        },
    }
    image_event = {
        "type": "event_callback",
        "uuid": "evt_bundle_verify_image",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "image",
                "content": json.dumps({"image_key": "img_1"}),
                "chat_id": "oc_1",
                "message_id": "om_bundle_verify_image",
            },
        },
    }
    gateway.handle_event({"type": "url_verification", "token": "good-token", "challenge": "challenge"}, async_dispatch=False)
    gateway.handle_event(text_event, async_dispatch=False)
    gateway.handle_event(image_event, async_dispatch=False)
    gateway.handle_event(text_event, async_dispatch=False)
    _record_advanced_live_evidence(gateway.smoke_recorder)
    _record_ws_runtime_evidence(
        gateway.logger,
        event_keys=_smoke_event_keys(gateway),
        ws_sdk_session_id="session-live-001",
    )
    bundle_dir = tmp_path / "bundle"
    bundle = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "smoke",
            "bundle",
            "--workspace",
            str(tmp_path),
            "--transport",
            "http",
            "--output",
            str(bundle_dir),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert bundle.returncode == 0

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [sys.executable, "scripts/verify_release.py", "--bundle", str(bundle_dir), "--json"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    data = json.loads(result.stdout)

    assert result.returncode == 0
    assert data["bundle"]["ok"] is True
    assert data["bundle"]["chain_ok"] is True
    assert data["bundle"]["redacted_chain_ok"] is True
    assert data["bundle"]["diagnostics_ok"] is True
    assert data["bundle"]["advanced_ok"] is True
    assert data["bundle"]["manifest"]["runtime"]["transport"] == "http"
    assert len(data["bundle"]["manifest"]["bundle_digest"]) == 64
    assert set(data["bundle"]["manifest"]["file_hashes"]) == {
        "advanced",
        "chain",
        "diagnostics",
        "event_store",
        "job_store",
        "runtime_log",
        "smoke_evidence",
    }


def test_release_verifier_accepts_bundle_with_handoff_records(tmp_path, monkeypatch):
    import subprocess
    import sys

    from yinyo import FeishuRuntimeGateway, JsonlEventStore, JsonlJobQueue, RuntimeLogger, SmokeEvidenceRecorder

    class Session:
        def is_duplicate(self, text, user_id):
            return False

    class Agent:
        session_manager = Session()

        def handle_message(self, user_id, chat_id, text, already_deduped=False, correlation_id=""):
            return {"text": "ok", "files": [{"path": "report.md"}], "run_id": "run-handoff-live"}

    class Adapter:
        agent = Agent()

        def add_reaction(self, message_id):
            return True

        def remove_reaction(self, message_id):
            return True

        def send_message(self, *args, **kwargs):
            return {"success": True, "message_ids": ["om_reply"], "fallback": bool(kwargs.get("files"))}

        def _download_image(self, image_key):
            return image_key

    class VisionAdapter:
        def describe(self, image_path, prompt):
            return {"description": "image description"}

    import yinyo.vision_adapter

    monkeypatch.setattr(yinyo.vision_adapter, "get_vision_adapter", lambda: VisionAdapter())
    gateway = FeishuRuntimeGateway(
        adapter=Adapter(),
        agent=Adapter.agent,
        verify_token="good-token",
        queue=JsonlJobQueue(str(tmp_path / "runtime_jobs.jsonl")),
        event_store=JsonlEventStore(str(tmp_path / "gateway_events.jsonl")),
        logger=RuntimeLogger(str(tmp_path / "runtime.jsonl")),
        smoke_recorder=SmokeEvidenceRecorder(str(tmp_path / "smoke_evidence.jsonl")),
    )
    text_event = {
        "type": "event_callback",
        "uuid": "evt_handoff_bundle_text",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": "hello"}),
                "chat_id": "oc_1",
                "message_id": "om_handoff_bundle_text",
            },
        },
    }
    image_event = {
        "type": "event_callback",
        "uuid": "evt_handoff_bundle_image",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "image",
                "content": json.dumps({"image_key": "img_1"}),
                "chat_id": "oc_1",
                "message_id": "om_handoff_bundle_image",
            },
        },
    }
    gateway.handle_event({"type": "url_verification", "token": "good-token", "challenge": "challenge"}, async_dispatch=False)
    gateway.handle_event(text_event, async_dispatch=False)
    gateway.handle_event(image_event, async_dispatch=False)
    gateway.handle_event(text_event, async_dispatch=False)
    _record_advanced_live_evidence(gateway.smoke_recorder)
    _record_ws_runtime_evidence(
        gateway.logger,
        event_keys=_smoke_event_keys(gateway),
        ws_sdk_session_id="session-live-001",
    )
    _write_replayable_handoff(
        tmp_path / "runs" / "run-handoff-live",
        run_id="run-handoff-live",
        correlation_id="evt_handoff_bundle_text",
        task="live handoff",
    )

    bundle_dir = tmp_path / "bundle"
    bundle = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "smoke",
            "bundle",
            "--workspace",
            str(tmp_path),
            "--transport",
            "http",
            "--handoff-dir",
            str(tmp_path / "runs"),
            "--output",
            str(bundle_dir),
            "--live-attestation-id",
            "real-attestation-001",
            "--feishu-app-id-hash",
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "--tenant-hash",
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "--ws-sdk-session-id",
            "session-live-001",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert bundle.returncode == 0

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [sys.executable, "scripts/verify_release.py", "--bundle", str(bundle_dir), "--json"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    data = json.loads(result.stdout)

    assert result.returncode == 0
    assert data["bundle"]["ok"] is True
    assert data["bundle"]["manifest"]["handoffs"]["records"] == 1
    assert data["bundle"]["manifest"]["handoffs"]["ready_records"] == 1
    assert data["bundle"]["manifest"]["frontier_readiness"]["handoff_ready_records"] == 1
    assert "handoff:run-handoff-live" in data["bundle"]["manifest"]["file_hashes"]
    assert "handoff_artifact:run-handoff-live:evidence_file" in data["bundle"]["manifest"]["file_hashes"]
    assert "handoff_artifact:run-handoff-live:manifest_file" in data["bundle"]["manifest"]["file_hashes"]
    assert (bundle_dir / "handoffs" / "run-handoff-live.handoff.json").is_file()
    assert (bundle_dir / "handoffs" / "run-handoff-live" / "evidence.jsonl").is_file()
    assert (bundle_dir / "handoffs" / "run-handoff-live" / "manifest.json").is_file()


def test_bundle_verifier_rejects_unreplayable_handoff(tmp_path):
    from yinyo import SmokeEvidenceRecorder, build_smoke_evidence_bundle, verify_smoke_evidence_bundle

    smoke_path = tmp_path / "smoke_evidence.jsonl"
    runtime_path = tmp_path / "runtime.jsonl"
    jobs_path = tmp_path / "runtime_jobs.jsonl"
    events_path = tmp_path / "gateway_events.jsonl"
    recorder = SmokeEvidenceRecorder(str(smoke_path))
    for scenario in ["url_verification", "text_message_reply", "image_message_reply", "card_fallback", "duplicate_callback"]:
        recorder.record(scenario, "passed", live=True, event_key="evt_bad_handoff")
    _record_advanced_live_evidence(recorder)
    runtime_path.write_text(
        "\n".join([
            json.dumps({"event": "service_start", "correlation_id": "service", "transport": "ws", "smoke_mode": False}),
            json.dumps({"event": "ws_transport_start", "correlation_id": "service"}),
            json.dumps({"event": "ws_event_received", "correlation_id": "evt_bad_handoff", "event_key": "evt_bad_handoff", "ack_latency_ms": 12.0, "ack_deadline_ms": 3000.0, "ack_within_deadline": True}),
            json.dumps({"event": "outbox_delivery", "correlation_id": "evt_bad_handoff", "event_key": "evt_bad_handoff", "success": True}),
            json.dumps({"event": "webhook_duplicate", "correlation_id": "evt_bad_handoff", "event_key": "evt_bad_handoff"}),
        ]) + "\n",
        encoding="utf-8",
    )
    jobs_path.write_text(
        json.dumps({"id": "job_1", "kind": "feishu_message", "status": "succeeded", "payload": {"event_key": "evt_bad_handoff"}, "result": {"run_id": "run-bad-handoff"}}) + "\n",
        encoding="utf-8",
    )
    events_path.write_text(json.dumps({"event_key": "evt_bad_handoff"}) + "\n", encoding="utf-8")
    bad_run = tmp_path / "runs" / "run-bad-handoff"
    bad_run.mkdir(parents=True)
    (bad_run / "handoff.json").write_text(json.dumps({
        "schema": "yinyo.handoff.v1",
        "run_id": "run-bad-handoff",
        "correlation_id": "evt_bad_handoff",
        "artifacts": {"evidence_file": "runs/run-bad-handoff/evidence.jsonl"},
        "provenance": {"source_audit": {"required": False, "satisfied": True}},
    }), encoding="utf-8")

    manifest = build_smoke_evidence_bundle(
        output_dir=str(tmp_path / "bundle"),
        smoke_path=str(smoke_path),
        log_path=str(runtime_path),
        job_store_path=str(jobs_path),
        event_store_path=str(events_path),
        runtime_lock_path=str(tmp_path / "yinyo_runtime.lock"),
        profile="local",
        transport="ws",
        handoff_dir=str(tmp_path / "runs"),
    )
    verified = verify_smoke_evidence_bundle(str(tmp_path / "bundle"))
    strict_verified = verify_smoke_evidence_bundle(str(tmp_path / "bundle"), require_run_handoff=True)

    state_handoff = next(
        item
        for item in manifest["frontier_readiness"]["checks"]
        if item["name"] == "State handoff transfer"
    )
    assert manifest["handoffs"]["records"] == 1
    assert manifest["handoffs"]["ready_records"] == 0
    assert manifest["frontier_readiness"]["handoff_ready_records"] == 0
    assert state_handoff["live_ok"] is False
    assert "bundle:handoff_ready_records" in state_handoff["missing"]
    assert manifest["frontier_readiness"]["ok"] is False
    assert verified["ok"] is False
    assert any("bundle handoff replay not ready: run-bad-handoff" in blocker for blocker in verified["blockers"])
    assert any("bundle handoff manifest_file missing: run-bad-handoff" in blocker for blocker in verified["blockers"])
    assert "bundle replayable run-level handoff missing" in strict_verified["blockers"]


def test_release_verifier_rejects_1_0_candidate_with_unreplayable_handoff_bundle(tmp_path):
    import subprocess
    import sys

    from yinyo import SmokeEvidenceRecorder, build_smoke_evidence_bundle

    smoke_path = tmp_path / "smoke_evidence.jsonl"
    runtime_path = tmp_path / "runtime.jsonl"
    jobs_path = tmp_path / "runtime_jobs.jsonl"
    events_path = tmp_path / "gateway_events.jsonl"
    recorder = SmokeEvidenceRecorder(str(smoke_path))
    for scenario in ["text_message_reply", "image_message_reply", "card_fallback", "duplicate_callback"]:
        recorder.record(scenario, "passed", live=True, event_key="evt_bad_candidate_handoff")
    _record_advanced_live_evidence(recorder)
    runtime_path.write_text(
        "\n".join([
            json.dumps({"event": "service_start", "correlation_id": "service", "transport": "ws", "smoke_mode": False}),
            json.dumps({"event": "ws_transport_start", "correlation_id": "service"}),
            json.dumps({"event": "ws_event_received", "correlation_id": "evt_bad_candidate_handoff", "event_key": "evt_bad_candidate_handoff", "ack_latency_ms": 12.0, "ack_deadline_ms": 3000.0, "ack_within_deadline": True}),
            json.dumps({"event": "outbox_delivery", "correlation_id": "evt_bad_candidate_handoff", "event_key": "evt_bad_candidate_handoff", "success": True}),
            json.dumps({"event": "webhook_duplicate", "correlation_id": "evt_bad_candidate_handoff", "event_key": "evt_bad_candidate_handoff"}),
        ]) + "\n",
        encoding="utf-8",
    )
    jobs_path.write_text(
        json.dumps({"id": "job_1", "kind": "feishu_message", "status": "succeeded", "payload": {"event_key": "evt_bad_candidate_handoff"}, "result": {"run_id": "run-bad-candidate-handoff"}}) + "\n",
        encoding="utf-8",
    )
    events_path.write_text(json.dumps({"event_key": "evt_bad_candidate_handoff"}) + "\n", encoding="utf-8")
    bad_run = tmp_path / "runs" / "run-bad-candidate-handoff"
    bad_run.mkdir(parents=True)
    (bad_run / "handoff.json").write_text(json.dumps({
        "schema": "yinyo.handoff.v1",
        "run_id": "run-bad-candidate-handoff",
        "correlation_id": "evt_bad_candidate_handoff",
        "artifacts": {"evidence_file": "runs/run-bad-candidate-handoff/evidence.jsonl"},
        "provenance": {"source_audit": {"required": False, "satisfied": True}},
    }), encoding="utf-8")
    build_smoke_evidence_bundle(
        output_dir=str(tmp_path / "bundle"),
        smoke_path=str(smoke_path),
        log_path=str(runtime_path),
        job_store_path=str(jobs_path),
        event_store_path=str(events_path),
        runtime_lock_path=str(tmp_path / "yinyo_runtime.lock"),
        profile="local",
        transport="ws",
        handoff_dir=str(tmp_path / "runs"),
    )

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [
            sys.executable,
            "scripts/verify_release.py",
            "--target",
            "1.0.0",
            "--bundle",
            str(tmp_path / "bundle"),
            "--candidate",
            "1.0.0",
            "--json",
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    data = json.loads(result.stdout)

    assert result.returncode == 1
    assert data["bundle"]["manifest"]["handoffs"]["records"] == 1
    assert data["bundle"]["manifest"]["handoffs"]["ready_records"] == 0
    assert "candidate 1.0.0 requires replayable run-level handoff in ws smoke bundle" in data["candidate"]["blockers"]


def test_bundle_verifier_skips_path_resolution_for_redacted_advanced_refs(tmp_path):
    from yinyo import (
        SmokeEvidenceRecorder,
        build_smoke_evidence_bundle,
        record_advanced_live_evidence,
        verify_smoke_evidence_bundle,
    )

    smoke_path = tmp_path / "smoke_evidence.jsonl"
    runtime_path = tmp_path / "runtime.jsonl"
    jobs_path = tmp_path / "runtime_jobs.jsonl"
    events_path = tmp_path / "gateway_events.jsonl"
    validation_path = tmp_path / "skills" / "retry-file-write" / "validation" / "validation.json"
    validation_dir = validation_path.parent
    validation_path.parent.mkdir(parents=True)
    validation_path.write_text(
        json.dumps({
            "schema": "yinyo.trace2skill_validation.v1",
            "skill_name": "retry-file-write",
            "failure_trace_ref": "trace2skill:abc",
            "passed": True,
            "checks": {
                "pre_skill_failure_reproduced": True,
                "post_skill_guardrail_applied": True,
                "pre_skill_command_failed_as_expected": True,
                "post_skill_command_passed": True,
            },
            "pre_skill_result": {"path": str(validation_dir / "pre-skill-regression.json"), "exit_code": 1},
            "post_skill_result": {"path": str(validation_dir / "post-skill-regression.json"), "exit_code": 0, "passed": True},
            "replay_result": {"passed": True, "exit_code": 0},
        }),
        encoding="utf-8",
    )
    skill_path = tmp_path / "skills" / "retry-file-write" / "meta.json"
    skill_path.write_text(json.dumps({"name": "retry-file-write", "status": "proven"}), encoding="utf-8")
    recorder = SmokeEvidenceRecorder(str(smoke_path))
    for scenario in ["url_verification", "text_message_reply", "image_message_reply", "card_fallback", "duplicate_callback"]:
        recorder.record(scenario, "passed", live=True, event_key="evt_1")
    for scenario, fields in [
        ("image_understanding", {"image_ref": "image-redacted-1"}),
        ("long_conversation", {"transcript_ref": "transcript-redacted-1"}),
        ("memory_supersession", {"memory_ref": "memory-redacted-1"}),
        ("deepseek_usage", {"model_usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}),
        ("partial_failure", {"failure_ref": "failure-redacted-1"}),
    ]:
        record_advanced_live_evidence(str(smoke_path), scenario, **fields)
    record_advanced_live_evidence(
        str(smoke_path),
        "trace2skill_promotion",
        failure_trace_ref="trace2skill:abc",
        skill_ref=str(skill_path),
        validation_ref=str(validation_path),
        promotion_status="proven",
        post_promotion_run_ref=str(validation_path),
    )
    runtime_path.write_text(
        "\n".join([
            json.dumps({"event": "webhook_accepted", "correlation_id": "evt_1", "event_key": "evt_1"}),
            json.dumps({"event": "outbox_delivery", "correlation_id": "evt_1", "event_key": "evt_1", "success": True}),
            json.dumps({"event": "webhook_duplicate", "correlation_id": "evt_1", "event_key": "evt_1"}),
        ]) + "\n",
        encoding="utf-8",
    )
    jobs_path.write_text(
        json.dumps({"id": "job_1", "kind": "feishu_message", "status": "succeeded", "payload": {"event_key": "evt_1"}, "result": {"run_id": "run-redacted-1"}}) + "\n",
        encoding="utf-8",
    )
    events_path.write_text(json.dumps({"event_key": "evt_1"}) + "\n", encoding="utf-8")

    bundle_dir = tmp_path / "bundle"
    manifest = build_smoke_evidence_bundle(
        output_dir=str(bundle_dir),
        smoke_path=str(smoke_path),
        log_path=str(runtime_path),
        job_store_path=str(jobs_path),
        event_store_path=str(events_path),
        runtime_lock_path=str(tmp_path / "yinyo_runtime.lock"),
        profile="local",
        transport="http",
    )
    verified = verify_smoke_evidence_bundle(str(bundle_dir))

    assert manifest["advanced"]["ref_unresolved"] == []
    assert manifest["advanced"]["ref_status"]["trace2skill_promotion"]["resolved"]["validation_ref"]["kind"] == "trace2skill_validation"
    attestation = manifest["advanced_ref_attestation"]
    assert attestation["schema"] == "yinyo.advanced_ref_attestation.v1"
    assert attestation["ok"] is True
    assert len(attestation["digest"]) == 64
    trace_attestation = attestation["scenarios"]["trace2skill_promotion"]
    assert trace_attestation["ref_resolution_schema"] == "yinyo.advanced_ref_resolution.v1"
    assert trace_attestation["refs"] == ["failure_trace_ref", "post_promotion_run_ref", "skill_ref", "validation_ref"]
    assert trace_attestation["proof_schema"] == "yinyo.advanced_live_proof.v1"
    assert trace_attestation["proof_refs"] == ["failure_trace_ref", "post_promotion_run_ref", "promotion_status", "skill_ref", "validation_ref"]
    assert not any("ref_unresolved" in blocker for blocker in verified["blockers"])
    assert not any("bundle advanced evidence does not match redacted JSONL" in blocker for blocker in verified["blockers"])


def test_bundle_verifier_rejects_tampered_advanced_ref_attestation(tmp_path):
    from yinyo import (
        SmokeEvidenceRecorder,
        build_smoke_evidence_bundle,
        record_advanced_live_evidence,
        verify_smoke_evidence_bundle,
    )

    smoke_path = tmp_path / "smoke_evidence.jsonl"
    runtime_path = tmp_path / "runtime.jsonl"
    jobs_path = tmp_path / "runtime_jobs.jsonl"
    events_path = tmp_path / "gateway_events.jsonl"
    recorder = SmokeEvidenceRecorder(str(smoke_path))
    for scenario in ["url_verification", "text_message_reply", "image_message_reply", "card_fallback", "duplicate_callback"]:
        recorder.record(scenario, "passed", live=True, event_key="evt_attest")
    for scenario, fields in [
        ("image_understanding", {"image_ref": "image-redacted-1"}),
        ("long_conversation", {"transcript_ref": "transcript-redacted-1"}),
        ("memory_supersession", {"memory_ref": "memory-redacted-1"}),
        ("trace2skill_promotion", {
            "failure_trace_ref": "trace2skill:abc",
            "skill_ref": "skill-redacted-1",
            "validation_ref": "validation-redacted-1",
            "promotion_status": "proven",
            "post_promotion_run_ref": "run-redacted-1",
        }),
        ("deepseek_usage", {"model_usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}),
        ("partial_failure", {"failure_ref": "failure-redacted-1"}),
    ]:
        record_advanced_live_evidence(str(smoke_path), scenario, **fields)
    runtime_path.write_text(
        "\n".join([
            json.dumps({"event": "webhook_accepted", "correlation_id": "evt_attest", "event_key": "evt_attest"}),
            json.dumps({"event": "outbox_delivery", "correlation_id": "evt_attest", "event_key": "evt_attest", "success": True}),
            json.dumps({"event": "webhook_duplicate", "correlation_id": "evt_attest", "event_key": "evt_attest"}),
        ]) + "\n",
        encoding="utf-8",
    )
    jobs_path.write_text(
        json.dumps({"id": "job_1", "kind": "feishu_message", "status": "succeeded", "payload": {"event_key": "evt_attest"}, "result": {"run_id": "run-redacted-1"}}) + "\n",
        encoding="utf-8",
    )
    events_path.write_text(json.dumps({"event_key": "evt_attest"}) + "\n", encoding="utf-8")

    bundle_dir = tmp_path / "bundle"
    build_smoke_evidence_bundle(
        output_dir=str(bundle_dir),
        smoke_path=str(smoke_path),
        log_path=str(runtime_path),
        job_store_path=str(jobs_path),
        event_store_path=str(events_path),
        runtime_lock_path=str(tmp_path / "yinyo_runtime.lock"),
        profile="local",
        transport="http",
    )
    manifest_path = bundle_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["advanced_ref_attestation"]["scenarios"]["trace2skill_promotion"]["ref_resolution_mode"] = "skipped_for_redacted_bundle"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    verified = verify_smoke_evidence_bundle(str(bundle_dir))

    assert verified["ok"] is False
    assert "bundle advanced ref attestation digest mismatch" in verified["blockers"]
    assert "bundle advanced ref attestation was built from redacted refs: trace2skill_promotion" in verified["blockers"]


def test_bundle_verifier_rejects_self_consistent_advanced_attestation_omission(tmp_path):
    import hashlib

    from yinyo import (
        SmokeEvidenceRecorder,
        build_smoke_evidence_bundle,
        record_advanced_live_evidence,
        verify_smoke_evidence_bundle,
    )

    def sha256_file(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def bundle_digest(file_hashes):
        payload = json.dumps(file_hashes, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    smoke_path = tmp_path / "smoke_evidence.jsonl"
    runtime_path = tmp_path / "runtime.jsonl"
    jobs_path = tmp_path / "runtime_jobs.jsonl"
    events_path = tmp_path / "gateway_events.jsonl"
    recorder = SmokeEvidenceRecorder(str(smoke_path))
    event_keys = {
        "url_verification": "evt_attest_omit_url",
        "text_message_reply": "evt_attest_omit_text",
        "image_message_reply": "evt_attest_omit_image",
        "card_fallback": "evt_attest_omit_card",
        "duplicate_callback": "evt_attest_omit_dup",
    }
    for scenario, event_key in event_keys.items():
        recorder.record(scenario, "passed", live=True, event_key=event_key)
    for scenario, fields in [
        ("image_understanding", {"image_ref": "image-redacted-1"}),
        ("long_conversation", {"transcript_ref": "transcript-redacted-1"}),
        ("memory_supersession", {"memory_ref": "memory-redacted-1"}),
        ("trace2skill_promotion", {
            "failure_trace_ref": "trace2skill:abc",
            "skill_ref": "skill-redacted-1",
            "validation_ref": "validation-redacted-1",
            "promotion_status": "proven",
            "post_promotion_run_ref": "run-redacted-1",
        }),
        ("deepseek_usage", {"model_usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}),
        ("partial_failure", {"failure_ref": "failure-redacted-1"}),
    ]:
        record_advanced_live_evidence(str(smoke_path), scenario, **fields)
    runtime_path.write_text(
        "\n".join([
            json.dumps({"event": "webhook_url_verification", "correlation_id": event_keys["url_verification"], "event_key": event_keys["url_verification"]}),
            json.dumps({"event": "outbox_delivery", "correlation_id": event_keys["text_message_reply"], "event_key": event_keys["text_message_reply"], "success": True}),
            json.dumps({"event": "outbox_delivery", "correlation_id": event_keys["image_message_reply"], "event_key": event_keys["image_message_reply"], "success": True}),
            json.dumps({"event": "outbox_delivery", "correlation_id": event_keys["card_fallback"], "event_key": event_keys["card_fallback"], "success": True}),
            json.dumps({"event": "webhook_duplicate", "correlation_id": event_keys["duplicate_callback"], "event_key": event_keys["duplicate_callback"]}),
        ]) + "\n",
        encoding="utf-8",
    )
    jobs_path.write_text(
        "\n".join(
            json.dumps({"id": f"job_{scenario}", "kind": "feishu_message", "status": "succeeded", "payload": {"event_key": event_key}, "result": {"run_id": "run-redacted-1"}})
            for scenario, event_key in event_keys.items()
        )
        + "\n",
        encoding="utf-8",
    )
    events_path.write_text("\n".join(json.dumps({"event_key": event_key}) for event_key in event_keys.values()) + "\n", encoding="utf-8")

    bundle_dir = tmp_path / "bundle"
    build_smoke_evidence_bundle(
        output_dir=str(bundle_dir),
        smoke_path=str(smoke_path),
        log_path=str(runtime_path),
        job_store_path=str(jobs_path),
        event_store_path=str(events_path),
        runtime_lock_path=str(tmp_path / "yinyo_runtime.lock"),
        profile="local",
        transport="http",
    )
    advanced_path = bundle_dir / "advanced.json"
    manifest_path = bundle_dir / "manifest.json"
    advanced = json.loads(advanced_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    advanced["passed"].remove("trace2skill_promotion")
    advanced["ref_status"].pop("trace2skill_promotion", None)
    manifest["advanced"] = advanced
    manifest["advanced_ref_attestation"]["scenarios"].pop("trace2skill_promotion", None)
    attestation_payload = {
        "schema": manifest["advanced_ref_attestation"]["schema"],
        "scenarios": manifest["advanced_ref_attestation"]["scenarios"],
        "blockers": manifest["advanced_ref_attestation"]["blockers"],
    }
    manifest["advanced_ref_attestation"]["digest"] = hashlib.sha256(
        json.dumps(attestation_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    advanced_path.write_text(json.dumps(advanced, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest["file_hashes"]["advanced"] = sha256_file(advanced_path)
    manifest["bundle_digest"] = bundle_digest(manifest["file_hashes"])
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    verified = verify_smoke_evidence_bundle(str(bundle_dir))

    assert verified["ok"] is False
    assert "bundle advanced evidence does not match redacted JSONL" in verified["blockers"]
    assert any("bundle advanced ref attestation does not match redacted JSONL" in blocker for blocker in verified["blockers"])


def test_release_verifier_rejects_1_0_candidate_with_http_bundle(tmp_path, monkeypatch):
    import subprocess
    import sys

    from yinyo import FeishuRuntimeGateway, JsonlEventStore, JsonlJobQueue, RuntimeLogger, SmokeEvidenceRecorder

    class Session:
        def is_duplicate(self, text, user_id):
            return False

    class Agent:
        session_manager = Session()

        def handle_message(self, user_id, chat_id, text, already_deduped=False, correlation_id=""):
            return {"text": "ok", "files": [{"path": "report.md"}], "run_id": f"run-{correlation_id}"}

    class Adapter:
        agent = Agent()

        def add_reaction(self, message_id):
            return True

        def remove_reaction(self, message_id):
            return True

        def send_message(self, *args, **kwargs):
            return {"success": True, "message_ids": ["om_reply"], "fallback": bool(kwargs.get("files"))}

        def _download_image(self, image_key):
            return image_key

    class VisionAdapter:
        def describe(self, image_path, prompt):
            return {"description": "image description"}

    import yinyo.vision_adapter

    monkeypatch.setattr(yinyo.vision_adapter, "get_vision_adapter", lambda: VisionAdapter())
    gateway = FeishuRuntimeGateway(
        adapter=Adapter(),
        agent=Adapter.agent,
        verify_token="good-token",
        queue=JsonlJobQueue(str(tmp_path / "runtime_jobs.jsonl")),
        event_store=JsonlEventStore(str(tmp_path / "gateway_events.jsonl")),
        logger=RuntimeLogger(str(tmp_path / "runtime.jsonl")),
        smoke_recorder=SmokeEvidenceRecorder(str(tmp_path / "smoke_evidence.jsonl")),
    )
    text_event = {
        "type": "event_callback",
        "uuid": "evt_bundle_target_text",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": "hello"}),
                "chat_id": "oc_1",
                "message_id": "om_bundle_target_text",
            },
        },
    }
    image_event = {
        "type": "event_callback",
        "uuid": "evt_bundle_target_image",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "image",
                "content": json.dumps({"image_key": "img_1"}),
                "chat_id": "oc_1",
                "message_id": "om_bundle_target_image",
            },
        },
    }
    gateway.handle_event({"type": "url_verification", "token": "good-token", "challenge": "challenge"}, async_dispatch=False)
    gateway.handle_event(text_event, async_dispatch=False)
    gateway.handle_event(image_event, async_dispatch=False)
    gateway.handle_event(text_event, async_dispatch=False)
    _record_advanced_live_evidence(gateway.smoke_recorder)
    _record_ws_runtime_evidence(
        gateway.logger,
        event_keys=_smoke_event_keys(gateway),
        ws_sdk_session_id="session-live-001",
    )

    bundle_dir = tmp_path / "bundle"
    bundle = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "smoke",
            "bundle",
            "--workspace",
            str(tmp_path),
            "--transport",
            "http",
            "--output",
            str(bundle_dir),
            "--live-attestation-id",
            "real-attestation-001",
            "--feishu-app-id-hash",
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "--tenant-hash",
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "--ws-sdk-session-id",
            "session-live-001",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert bundle.returncode == 0

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [
            sys.executable,
            "scripts/verify_release.py",
            "--target",
            "1.0.0",
            "--bundle",
            str(bundle_dir),
            "--candidate",
            "1.0.0",
            "--json",
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    data = json.loads(result.stdout)
    items = {item["id"]: item for item in data["items"]}

    assert result.returncode == 1
    assert data["ok"] is False
    assert items["R1-03"]["passed"] is True
    assert items["R1-07"]["passed"] is False
    assert "verified bundle is not ws long-connection evidence" in items["R1-07"]["blockers"]
    assert data["bundle"]["ok"] is True
    assert data["bundle"]["manifest"]["runtime"]["transport"] == "http"
    assert data["bundle"]["advanced_ok"] is True
    assert data["candidate"]["ok"] is False
    assert "candidate 1.0.0 requires a ws long-connection smoke bundle" in data["candidate"]["blockers"]
    assert data["candidate"]["requires_tag"] == "v1.0.0"


def test_release_verifier_rejects_1_0_candidate_when_package_metadata_is_alpha(tmp_path, monkeypatch):
    import subprocess
    import sys

    from yinyo import FeishuRuntimeGateway, JsonlEventStore, JsonlJobQueue, RuntimeLogger, SmokeEvidenceRecorder

    class Session:
        def is_duplicate(self, text, user_id):
            return False

    class Agent:
        session_manager = Session()

        def handle_message(self, user_id, chat_id, text, already_deduped=False, correlation_id=""):
            return {"text": "ok", "files": [{"path": "report.md"}], "run_id": f"run-{correlation_id}"}

    class Adapter:
        agent = Agent()

        def add_reaction(self, message_id):
            return True

        def remove_reaction(self, message_id):
            return True

        def send_message(self, *args, **kwargs):
            return {"success": True, "message_ids": ["om_reply"], "fallback": bool(kwargs.get("files"))}

        def _download_image(self, image_key):
            return image_key

    class VisionAdapter:
        def describe(self, image_path, prompt):
            return {"description": "image description"}

    import yinyo.vision_adapter

    monkeypatch.setattr(yinyo.vision_adapter, "get_vision_adapter", lambda: VisionAdapter())
    gateway = FeishuRuntimeGateway(
        adapter=Adapter(),
        agent=Adapter.agent,
        verify_token="good-token",
        queue=JsonlJobQueue(str(tmp_path / "runtime_jobs.jsonl")),
        event_store=JsonlEventStore(str(tmp_path / "gateway_events.jsonl")),
        logger=RuntimeLogger(str(tmp_path / "runtime.jsonl")),
        smoke_recorder=SmokeEvidenceRecorder(str(tmp_path / "smoke_evidence.jsonl")),
    )
    text_event = {
        "type": "event_callback",
        "uuid": "evt_bundle_target_ws_text",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": "hello"}),
                "chat_id": "oc_1",
                "message_id": "om_bundle_target_ws_text",
            },
        },
    }
    image_event = {
        "type": "event_callback",
        "uuid": "evt_bundle_target_ws_image",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "image",
                "content": json.dumps({"image_key": "img_1"}),
                "chat_id": "oc_1",
                "message_id": "om_bundle_target_ws_image",
            },
        },
    }
    gateway.handle_event(text_event, async_dispatch=False)
    gateway.handle_event(image_event, async_dispatch=False)
    gateway.handle_event(text_event, async_dispatch=False)
    _record_advanced_live_evidence(gateway.smoke_recorder)
    _record_ws_runtime_evidence(
        gateway.logger,
        event_keys=_smoke_event_keys(gateway),
        ws_sdk_session_id="session-live-001",
    )
    _write_replayable_handoff(
        tmp_path / "runs" / "run-ws-handoff",
        run_id="run-ws-handoff",
        correlation_id="evt_bundle_target_ws_text",
        task="ws release handoff",
    )

    bundle_dir = tmp_path / "bundle"
    bundle = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "smoke",
            "bundle",
            "--workspace",
            str(tmp_path),
            "--transport",
            "ws",
            "--handoff-dir",
            str(tmp_path / "runs"),
            "--output",
            str(bundle_dir),
            "--live-attestation-id",
            "real-attestation-001",
            "--feishu-app-id-hash",
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "--tenant-hash",
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "--ws-sdk-session-id",
            "session-live-001",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert bundle.returncode == 0

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [
            sys.executable,
            "scripts/verify_release.py",
            "--target",
            "1.0.0",
            "--bundle",
            str(bundle_dir),
            "--candidate",
            "1.0.0",
            "--json",
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    data = json.loads(result.stdout)
    items = {item["id"]: item for item in data["items"]}

    assert result.returncode == 1
    assert data["ok"] is False
    assert items["R1-03"]["passed"] is True
    assert items["R1-07"]["passed"] is True
    assert data["bundle"]["ok"] is True
    assert data["bundle"]["manifest"]["runtime"]["transport"] == "ws"
    assert data["bundle"]["manifest"]["handoffs"]["records"] == 1
    assert data["bundle"]["manifest"]["handoffs"]["ready_records"] == 1
    manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    assert "url_verification" not in manifest["chain"]["smoke"]["required"]
    assert data["bundle"]["advanced_ok"] is True
    assert data["candidate"]["ok"] is False
    assert "candidate 1.0.0 requires pyproject version 1.0.0, found 1.0.0rc1" in data["candidate"]["blockers"]
    assert "candidate 1.0.0 requires module version 1.0.0, found 1.0.0rc1" in data["candidate"]["blockers"]
    assert "candidate 1.0.0 requires changelog heading 1.0.0" in data["candidate"]["blockers"]
    assert not any("live provenance fields" in blocker for blocker in data["candidate"]["blockers"])
    assert data["candidate"]["requires_tag"] == "v1.0.0"


def test_prepare_release_metadata_updates_all_external_version_surfaces():
    import scripts.prepare_release_metadata as prepare

    replacements = prepare._release_replacements("1.0.0", "1.0.0")

    assert 'version = "1.0.0"' in replacements["pyproject.toml"]
    assert '__version__ = "1.0.0"' in replacements["yinyo/__init__.py"]
    assert "YINYO 1.0.0" in replacements["yinyo/__init__.py"]
    assert "version-1.0.0-2ea043" in replacements["README.md"]
    assert "Current external version: `1.0.0`" in replacements["README.md"]
    assert "Python package version: `1.0.0`" in replacements["README.md"]
    assert "当前外部版本：`1.0.0`" in replacements["README.zh-CN.md"]
    assert "Python 包版本：`1.0.0`" in replacements["README.zh-CN.md"]
    assert "| Product version | `1.0.0` |" in replacements["docs/versioning.md"]
    assert "| Python package version | `1.0.0` |" in replacements["docs/versioning.md"]
    assert "| Release maturity | Stable |" in replacements["docs/versioning.md"]
    assert "## 1.0.0" in replacements["CHANGELOG.md"]
    assert "## 0.1.0-alpha.1" in replacements["CHANGELOG.md"]
    assert "release-1.0.0-2ea043" in replacements["MAINTENANCE.md"]


def test_prepare_release_metadata_dry_run_does_not_write_files():
    import os
    import subprocess
    import sys

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    before = open(os.path.join(repo, "pyproject.toml"), encoding="utf-8").read()
    result = subprocess.run(
        [sys.executable, "scripts/prepare_release_metadata.py", "--version", "1.0.0"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    after = open(os.path.join(repo, "pyproject.toml"), encoding="utf-8").read()

    assert result.returncode == 0
    assert "Dry run: release metadata would update" in result.stdout
    assert "pyproject.toml" in result.stdout
    assert before == after


def test_prepare_release_metadata_apply_1_0_requires_verified_bundle():
    import os
    import subprocess
    import sys

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [sys.executable, "scripts/prepare_release_metadata.py", "--version", "1.0.0", "--apply"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "--verified-bundle" in result.stderr


def test_prepare_release_metadata_dry_run_1_0_rejects_invalid_verified_bundle(tmp_path):
    import os
    import subprocess
    import sys

    bundle = tmp_path / "bundle"
    bundle.mkdir()
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [
            sys.executable,
            "scripts/prepare_release_metadata.py",
            "--version",
            "1.0.0",
            "--verified-bundle",
            str(bundle),
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "verified bundle check failed" in result.stderr
    assert "Dry run: release metadata would update" not in result.stdout


def test_prepare_release_metadata_apply_1_0_rejects_invalid_bundle(tmp_path):
    import os
    import subprocess
    import sys

    bundle = tmp_path / "bundle"
    bundle.mkdir()
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [
            sys.executable,
            "scripts/prepare_release_metadata.py",
            "--version",
            "1.0.0",
            "--apply",
            "--verified-bundle",
            str(bundle),
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "verified bundle check failed" in result.stderr


def test_cli_smoke_bundle_inherits_ws_session_id_from_config(tmp_path, monkeypatch):
    import subprocess
    import sys

    from yinyo import FeishuRuntimeGateway, JsonlEventStore, JsonlJobQueue, RuntimeLogger, SmokeEvidenceRecorder

    class Session:
        def is_duplicate(self, text, user_id):
            return False

    class Agent:
        session_manager = Session()

        def handle_message(self, user_id, chat_id, text, already_deduped=False, correlation_id=""):
            return {"text": "ok", "files": [{"path": "report.md"}], "run_id": f"run-{correlation_id}"}

    class Adapter:
        agent = Agent()

        def add_reaction(self, message_id):
            return True

        def remove_reaction(self, message_id):
            return True

        def send_message(self, *args, **kwargs):
            return {"success": True, "message_ids": ["om_reply"], "fallback": bool(kwargs.get("files"))}

        def _download_image(self, image_key):
            return image_key

    class VisionAdapter:
        def describe(self, image_path, prompt):
            return {"description": "image description"}

    import yinyo.vision_adapter

    monkeypatch.setattr(yinyo.vision_adapter, "get_vision_adapter", lambda: VisionAdapter())
    gateway = FeishuRuntimeGateway(
        adapter=Adapter(),
        agent=Adapter.agent,
        verify_token="good-token",
        queue=JsonlJobQueue(str(tmp_path / "runtime_jobs.jsonl")),
        event_store=JsonlEventStore(str(tmp_path / "gateway_events.jsonl")),
        logger=RuntimeLogger(str(tmp_path / "runtime.jsonl")),
        smoke_recorder=SmokeEvidenceRecorder(str(tmp_path / "smoke_evidence.jsonl")),
    )
    text_event = {
        "type": "event_callback",
        "uuid": "evt_config_session_text",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": "hello"}),
                "chat_id": "oc_1",
                "message_id": "om_config_session_text",
            },
        },
    }
    image_event = {
        "type": "event_callback",
        "uuid": "evt_config_session_image",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "image",
                "content": json.dumps({"image_key": "img_1"}),
                "chat_id": "oc_1",
                "message_id": "om_config_session_image",
            },
        },
    }
    gateway.handle_event(text_event, async_dispatch=False)
    gateway.handle_event(image_event, async_dispatch=False)
    gateway.handle_event(text_event, async_dispatch=False)
    _record_advanced_live_evidence(gateway.smoke_recorder)
    _record_ws_runtime_evidence(
        gateway.logger,
        event_keys=_smoke_event_keys(gateway),
        ws_sdk_session_id="session-live-config-001",
    )
    _write_replayable_handoff(
        tmp_path / "runs" / "run-config-session",
        run_id="run-config-session",
        correlation_id="evt_config_session_text",
        task="config session bundle",
    )
    config_path = tmp_path / "yinyo.env"
    config_path.write_text(
        "\n".join([
            f"workspace={tmp_path}",
            "transport=ws",
            "app_id=app",
            "app_secret=super-secret",
            "deepseek_api_key=sk-secret",
            "ws_sdk_session_id=session-live-config-001",
        ]),
        encoding="utf-8",
    )
    bundle_dir = tmp_path / "bundle"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "smoke",
            "bundle",
            "--config",
            str(config_path),
            "--handoff-dir",
            str(tmp_path / "runs"),
            "--output",
            str(bundle_dir),
            "--live-attestation-id",
            "real-attestation-001",
            "--tenant-hash",
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    data = json.loads(result.stdout)

    assert result.returncode == 0
    assert data["live_provenance"]["ws_sdk_session_id"] == "session-live-config-001"
    assert data["live_provenance"]["feishu_app_id_hash"] == hashlib.sha256(b"app").hexdigest()
    assert data["runtime_verification"]["ok"] is True
    assert "super-secret" not in result.stdout
    assert "sk-secret" not in result.stdout


def test_cli_smoke_bundle_rejects_ws_session_id_config_flag_mismatch(tmp_path):
    import subprocess
    import sys

    config_path = tmp_path / "yinyo.env"
    config_path.write_text(
        "\n".join([
            f"workspace={tmp_path}",
            "transport=ws",
            "app_id=app",
            "app_secret=super-secret",
            "deepseek_api_key=sk-secret",
            "ws_sdk_session_id=session-live-config-001",
        ]),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "smoke",
            "bundle",
            "--config",
            str(config_path),
            "--output",
            str(tmp_path / "bundle"),
            "--ws-sdk-session-id",
            "session-live-other-002",
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "must match ws_sdk_session_id from config" in result.stderr
    assert "service_start, ws_transport_start, and the bundle manifest" in result.stderr
    assert "super-secret" not in result.stderr
    assert "sk-secret" not in result.stderr


def test_cli_smoke_bundle_rejects_feishu_app_id_hash_config_flag_mismatch(tmp_path):
    import subprocess
    import sys

    config_path = tmp_path / "yinyo.env"
    config_path.write_text(
        "\n".join([
            f"workspace={tmp_path}",
            "transport=ws",
            "app_id=app",
            "app_secret=super-secret",
            "deepseek_api_key=sk-secret",
            "ws_sdk_session_id=session-live-config-001",
        ]),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "smoke",
            "bundle",
            "--config",
            str(config_path),
            "--output",
            str(tmp_path / "bundle"),
            "--feishu-app-id-hash",
            "c" * 64,
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "must match sha256(app_id) from config" in result.stderr
    assert "live provenance app marker" in result.stderr
    assert not (tmp_path / "bundle" / "manifest.json").exists()
    assert "super-secret" not in result.stderr
    assert "sk-secret" not in result.stderr


def test_cli_smoke_bundle_accepts_matching_ws_session_id_arg_and_config(tmp_path, monkeypatch):
    import subprocess
    import sys

    from yinyo import FeishuRuntimeGateway, JsonlEventStore, JsonlJobQueue, RuntimeLogger, SmokeEvidenceRecorder

    class Session:
        def is_duplicate(self, text, user_id):
            return False

    class Agent:
        session_manager = Session()

        def handle_message(self, user_id, chat_id, text, already_deduped=False, correlation_id=""):
            return {"text": "ok", "files": [{"path": "report.md"}], "run_id": f"run-{correlation_id}"}

    class Adapter:
        agent = Agent()

        def add_reaction(self, message_id):
            return True

        def remove_reaction(self, message_id):
            return True

        def send_message(self, *args, **kwargs):
            return {"success": True, "message_ids": ["om_reply"], "fallback": bool(kwargs.get("files"))}

        def _download_image(self, image_key):
            return image_key

    class VisionAdapter:
        def describe(self, image_path, prompt):
            return {"description": "image description"}

    import yinyo.vision_adapter

    monkeypatch.setattr(yinyo.vision_adapter, "get_vision_adapter", lambda: VisionAdapter())
    gateway = FeishuRuntimeGateway(
        adapter=Adapter(),
        agent=Adapter.agent,
        verify_token="good-token",
        queue=JsonlJobQueue(str(tmp_path / "runtime_jobs.jsonl")),
        event_store=JsonlEventStore(str(tmp_path / "gateway_events.jsonl")),
        logger=RuntimeLogger(str(tmp_path / "runtime.jsonl")),
        smoke_recorder=SmokeEvidenceRecorder(str(tmp_path / "smoke_evidence.jsonl")),
    )
    text_event = {
        "type": "event_callback",
        "uuid": "evt_matching_session_text",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": "hello"}),
                "chat_id": "oc_1",
                "message_id": "om_matching_session_text",
            },
        },
    }
    image_event = {
        "type": "event_callback",
        "uuid": "evt_matching_session_image",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "image",
                "content": json.dumps({"image_key": "img_1"}),
                "chat_id": "oc_1",
                "message_id": "om_matching_session_image",
            },
        },
    }
    gateway.handle_event(text_event, async_dispatch=False)
    gateway.handle_event(image_event, async_dispatch=False)
    gateway.handle_event(text_event, async_dispatch=False)
    _record_advanced_live_evidence(gateway.smoke_recorder)
    _record_ws_runtime_evidence(
        gateway.logger,
        event_keys=_smoke_event_keys(gateway),
        ws_sdk_session_id="session-live-config-001",
    )
    _write_replayable_handoff(
        tmp_path / "runs" / "run-matching-session",
        run_id="run-matching-session",
        correlation_id="evt_matching_session_text",
        task="matching session bundle",
    )
    config_path = tmp_path / "yinyo.env"
    config_path.write_text(
        "\n".join([
            f"workspace={tmp_path}",
            "transport=ws",
            "app_id=app",
            "app_secret=super-secret",
            "deepseek_api_key=sk-secret",
            "ws_sdk_session_id=session-live-config-001",
        ]),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "smoke",
            "bundle",
            "--config",
            str(config_path),
            "--handoff-dir",
            str(tmp_path / "runs"),
            "--output",
            str(tmp_path / "bundle"),
            "--live-attestation-id",
            "real-attestation-001",
            "--feishu-app-id-hash",
            hashlib.sha256(b"app").hexdigest(),
            "--tenant-hash",
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "--ws-sdk-session-id",
            "session-live-config-001",
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    data = json.loads(result.stdout)

    assert result.returncode == 0
    assert data["live_provenance"]["ws_sdk_session_id"] == "session-live-config-001"
    assert data["live_provenance"]["feishu_app_id_hash"] == hashlib.sha256(b"app").hexdigest()
    assert "must match ws_sdk_session_id from config" not in result.stderr
    assert "must match sha256(app_id) from config" not in result.stderr


def test_release_candidate_rejects_ws_bundle_without_frontier_readiness(tmp_path, monkeypatch):
    import subprocess
    import sys

    from yinyo import FeishuRuntimeGateway, JsonlEventStore, JsonlJobQueue, RuntimeLogger, SmokeEvidenceRecorder

    class Session:
        def is_duplicate(self, text, user_id):
            return False

    class Agent:
        session_manager = Session()

        def handle_message(self, user_id, chat_id, text, already_deduped=False, correlation_id=""):
            return {"text": "ok", "files": [{"path": "report.md"}], "run_id": f"run-{correlation_id}"}

    class Adapter:
        agent = Agent()

        def add_reaction(self, message_id):
            return True

        def remove_reaction(self, message_id):
            return True

        def send_message(self, *args, **kwargs):
            return {"success": True, "message_ids": ["om_reply"], "fallback": bool(kwargs.get("files"))}

        def _download_image(self, image_key):
            return image_key

    class VisionAdapter:
        def describe(self, image_path, prompt):
            return {"description": "image description"}

    import yinyo.vision_adapter

    monkeypatch.setattr(yinyo.vision_adapter, "get_vision_adapter", lambda: VisionAdapter())
    gateway = FeishuRuntimeGateway(
        adapter=Adapter(),
        agent=Adapter.agent,
        verify_token="good-token",
        queue=JsonlJobQueue(str(tmp_path / "runtime_jobs.jsonl")),
        event_store=JsonlEventStore(str(tmp_path / "gateway_events.jsonl")),
        logger=RuntimeLogger(str(tmp_path / "runtime.jsonl")),
        smoke_recorder=SmokeEvidenceRecorder(str(tmp_path / "smoke_evidence.jsonl")),
    )
    text_event = {
        "type": "event_callback",
        "uuid": "evt_frontier_candidate_text",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": "hello"}),
                "chat_id": "oc_1",
                "message_id": "om_frontier_candidate_text",
            },
        },
    }
    image_event = {
        "type": "event_callback",
        "uuid": "evt_frontier_candidate_image",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "image",
                "content": json.dumps({"image_key": "img_1"}),
                "chat_id": "oc_1",
                "message_id": "om_frontier_candidate_image",
            },
        },
    }
    gateway.handle_event(text_event, async_dispatch=False)
    gateway.handle_event(image_event, async_dispatch=False)
    gateway.handle_event(text_event, async_dispatch=False)
    _record_advanced_live_evidence(gateway.smoke_recorder)
    _record_ws_runtime_evidence(
        gateway.logger,
        event_keys=_smoke_event_keys(gateway),
        ws_sdk_session_id="session-live-001",
    )
    _write_replayable_handoff(
        tmp_path / "runs" / "run-frontier-candidate",
        run_id="run-frontier-candidate",
        correlation_id="evt_frontier_candidate_text",
        task="frontier candidate handoff",
    )

    bundle_dir = tmp_path / "bundle"
    bundle = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "smoke",
            "bundle",
            "--workspace",
            str(tmp_path),
            "--transport",
            "ws",
            "--handoff-dir",
            str(tmp_path / "runs"),
            "--output",
            str(bundle_dir),
            "--live-attestation-id",
            "real-attestation-001",
            "--feishu-app-id-hash",
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "--tenant-hash",
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "--ws-sdk-session-id",
            "session-live-001",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert bundle.returncode == 0
    manifest_path = bundle_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["frontier_readiness"]["ok"] = False
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [
            sys.executable,
            "scripts/verify_release.py",
            "--target",
            "1.0.0",
            "--bundle",
            str(bundle_dir),
            "--candidate",
            "1.0.0",
            "--json",
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    data = json.loads(result.stdout)

    assert result.returncode == 1
    assert data["candidate"]["ok"] is False
    assert "candidate 1.0.0 requires frontier readiness in verified bundle" in data["candidate"]["blockers"]


def test_release_verifier_rejects_1_0_ws_bundle_without_run_handoff(tmp_path, monkeypatch):
    import subprocess
    import sys

    from yinyo import FeishuRuntimeGateway, JsonlEventStore, JsonlJobQueue, RuntimeLogger, SmokeEvidenceRecorder

    class Session:
        def is_duplicate(self, text, user_id):
            return False

    class Agent:
        session_manager = Session()

        def handle_message(self, user_id, chat_id, text, already_deduped=False, correlation_id=""):
            return {"text": "ok", "files": [{"path": "report.md"}], "run_id": f"run-{correlation_id}"}

    class Adapter:
        agent = Agent()

        def add_reaction(self, message_id):
            return True

        def remove_reaction(self, message_id):
            return True

        def send_message(self, *args, **kwargs):
            return {"success": True, "message_ids": ["om_reply"], "fallback": bool(kwargs.get("files"))}

        def _download_image(self, image_key):
            return image_key

    class VisionAdapter:
        def describe(self, image_path, prompt):
            return {"description": "image description"}

    import yinyo.vision_adapter

    monkeypatch.setattr(yinyo.vision_adapter, "get_vision_adapter", lambda: VisionAdapter())
    gateway = FeishuRuntimeGateway(
        adapter=Adapter(),
        agent=Adapter.agent,
        verify_token="good-token",
        queue=JsonlJobQueue(str(tmp_path / "runtime_jobs.jsonl")),
        event_store=JsonlEventStore(str(tmp_path / "gateway_events.jsonl")),
        logger=RuntimeLogger(str(tmp_path / "runtime.jsonl")),
        smoke_recorder=SmokeEvidenceRecorder(str(tmp_path / "smoke_evidence.jsonl")),
    )
    text_event = {
        "type": "event_callback",
        "uuid": "evt_bundle_no_handoff_text",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": "hello"}),
                "chat_id": "oc_1",
                "message_id": "om_bundle_no_handoff_text",
            },
        },
    }
    image_event = {
        "type": "event_callback",
        "uuid": "evt_bundle_no_handoff_image",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "image",
                "content": json.dumps({"image_key": "img_1"}),
                "chat_id": "oc_1",
                "message_id": "om_bundle_no_handoff_image",
            },
        },
    }
    gateway.handle_event(text_event, async_dispatch=False)
    gateway.handle_event(image_event, async_dispatch=False)
    gateway.handle_event(text_event, async_dispatch=False)
    _record_advanced_live_evidence(gateway.smoke_recorder)
    _record_ws_runtime_evidence(gateway.logger, event_keys=_smoke_event_keys(gateway))

    bundle_dir = tmp_path / "bundle"
    bundle = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "smoke",
            "bundle",
            "--workspace",
            str(tmp_path),
            "--transport",
            "ws",
            "--output",
            str(bundle_dir),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    data = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))

    assert bundle.returncode == 1
    assert data["ok"] is False
    assert data["frontier_readiness"]["handoff_records"] == 0
    assert data["frontier_readiness"]["handoff_ready_records"] == 0
    state_handoff = next(
        item for item in data["frontier_readiness"]["checks"] if item["name"] == "State handoff transfer"
    )
    assert state_handoff["live_ok"] is False
    assert "bundle:handoff_ready_records" in state_handoff["missing"]
    assert "handoff" in data["handoff_summary"]["blocking_layers"]


def test_release_verifier_rejects_ws_bundle_without_ws_runtime_log(tmp_path, monkeypatch):
    import subprocess
    import sys

    from yinyo import FeishuRuntimeGateway, JsonlEventStore, JsonlJobQueue, RuntimeLogger, SmokeEvidenceRecorder

    class Session:
        def is_duplicate(self, text, user_id):
            return False

    class Agent:
        session_manager = Session()

        def handle_message(self, user_id, chat_id, text, already_deduped=False, correlation_id=""):
            return {"text": "ok", "files": [{"path": "report.md"}], "run_id": f"run-{correlation_id}"}

    class Adapter:
        agent = Agent()

        def add_reaction(self, message_id):
            return True

        def remove_reaction(self, message_id):
            return True

        def send_message(self, *args, **kwargs):
            return {"success": True, "message_ids": ["om_reply"], "fallback": bool(kwargs.get("files"))}

        def _download_image(self, image_key):
            return image_key

    class VisionAdapter:
        def describe(self, image_path, prompt):
            return {"description": "image description"}

    import yinyo.vision_adapter

    monkeypatch.setattr(yinyo.vision_adapter, "get_vision_adapter", lambda: VisionAdapter())
    gateway = FeishuRuntimeGateway(
        adapter=Adapter(),
        agent=Adapter.agent,
        verify_token="good-token",
        queue=JsonlJobQueue(str(tmp_path / "runtime_jobs.jsonl")),
        event_store=JsonlEventStore(str(tmp_path / "gateway_events.jsonl")),
        logger=RuntimeLogger(str(tmp_path / "runtime.jsonl")),
        smoke_recorder=SmokeEvidenceRecorder(str(tmp_path / "smoke_evidence.jsonl")),
    )
    text_event = {
        "type": "event_callback",
        "uuid": "evt_bundle_ws_missing_text",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": "hello"}),
                "chat_id": "oc_1",
                "message_id": "om_bundle_ws_missing_text",
            },
        },
    }
    image_event = {
        "type": "event_callback",
        "uuid": "evt_bundle_ws_missing_image",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "image",
                "content": json.dumps({"image_key": "img_1"}),
                "chat_id": "oc_1",
                "message_id": "om_bundle_ws_missing_image",
            },
        },
    }
    gateway.handle_event({"type": "url_verification", "token": "good-token", "challenge": "challenge"}, async_dispatch=False)
    gateway.handle_event(text_event, async_dispatch=False)
    gateway.handle_event(image_event, async_dispatch=False)
    gateway.handle_event(text_event, async_dispatch=False)
    _record_advanced_live_evidence(gateway.smoke_recorder)

    bundle_dir = tmp_path / "bundle"
    bundle = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "smoke",
            "bundle",
            "--workspace",
            str(tmp_path),
            "--transport",
            "ws",
            "--output",
            str(bundle_dir),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert bundle.returncode == 1
    assert "ws_event_received" in bundle.stdout

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [
            sys.executable,
            "scripts/verify_release.py",
            "--target",
            "1.0.0",
            "--bundle",
            str(bundle_dir),
            "--candidate",
            "1.0.0",
            "--json",
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    data = json.loads(result.stdout)

    assert result.returncode == 1
    assert data["bundle"]["ok"] is False
    assert any("service_start" in item for item in data["bundle"]["blockers"])
    assert any("ws_transport_start" in item for item in data["bundle"]["blockers"])
    assert any("ws_event_received" in item for item in data["bundle"]["blockers"])


def test_bundle_verifier_rejects_ws_runtime_verification_manifest_drift(tmp_path):
    from yinyo import RuntimeLogger, SmokeEvidenceRecorder, build_smoke_evidence_bundle, verify_smoke_evidence_bundle

    smoke_path = tmp_path / "smoke_evidence.jsonl"
    runtime_path = tmp_path / "runtime.jsonl"
    jobs_path = tmp_path / "runtime_jobs.jsonl"
    events_path = tmp_path / "gateway_events.jsonl"
    recorder = SmokeEvidenceRecorder(str(smoke_path))
    event_keys = {
        "text_message_reply": "evt_text",
        "image_message_reply": "evt_image",
        "card_fallback": "evt_card",
        "duplicate_callback": "evt_dup",
    }
    for scenario, event_key in event_keys.items():
        recorder.record(scenario, "passed", live=True, event_key=event_key)
    _record_advanced_live_evidence(recorder)
    logger = RuntimeLogger(str(runtime_path))
    _record_ws_runtime_evidence(logger, event_keys=list(event_keys.values()))
    for scenario in ("text_message_reply", "image_message_reply", "card_fallback"):
        logger.record("outbox_delivery", correlation_id=event_keys[scenario], event_key=event_keys[scenario], success=True)
    logger.record("webhook_duplicate", correlation_id=event_keys["duplicate_callback"], event_key=event_keys["duplicate_callback"])
    jobs_path.write_text(
        "\n".join(
            json.dumps({
                "id": f"job_{scenario}",
                "kind": "feishu_message",
                "status": "succeeded",
                "payload": {"event_key": event_key},
                "result": {"run_id": f"run-{scenario}"},
            })
            for scenario, event_key in event_keys.items()
        )
        + "\n",
        encoding="utf-8",
    )
    events_path.write_text("\n".join(json.dumps({"event_key": event_key}) for event_key in event_keys.values()) + "\n", encoding="utf-8")
    bundle_dir = tmp_path / "bundle"
    build_smoke_evidence_bundle(
        output_dir=str(bundle_dir),
        smoke_path=str(smoke_path),
        log_path=str(runtime_path),
        job_store_path=str(jobs_path),
        event_store_path=str(events_path),
        runtime_lock_path=str(tmp_path / "yinyo_runtime.lock"),
        profile="local",
        transport="ws",
    )
    manifest_path = bundle_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["runtime_verification"] = {
        "schema": "yinyo.runtime_bundle_verification.v1",
        "ok": False,
        "blockers": ["tampered"],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    verified = verify_smoke_evidence_bundle(str(bundle_dir))

    assert verified["ok"] is False
    assert verified["manifest"]["runtime_verification"]["ok"] is False
    assert "bundle runtime verification does not match redacted runtime log" in verified["blockers"]
    assert "bundle runtime verification blockers do not match redacted runtime log" in verified["blockers"]


def test_bundle_verifier_cross_checks_ws_session_provenance_with_runtime_log(tmp_path):
    from yinyo import RuntimeLogger, SmokeEvidenceRecorder, build_smoke_evidence_bundle, verify_smoke_evidence_bundle

    smoke_path = tmp_path / "smoke_evidence.jsonl"
    runtime_path = tmp_path / "runtime.jsonl"
    jobs_path = tmp_path / "runtime_jobs.jsonl"
    events_path = tmp_path / "gateway_events.jsonl"
    recorder = SmokeEvidenceRecorder(str(smoke_path))
    event_keys = {
        "text_message_reply": "evt_session_text",
        "image_message_reply": "evt_session_image",
        "card_fallback": "evt_session_card",
        "duplicate_callback": "evt_session_dup",
    }
    for scenario, event_key in event_keys.items():
        recorder.record(scenario, "passed", live=True, event_key=event_key)
    _record_advanced_live_evidence(recorder)
    logger = RuntimeLogger(str(runtime_path))
    _record_ws_runtime_evidence(logger, event_keys=list(event_keys.values()), ws_sdk_session_id="session-live-runtime-001")
    for scenario in ("text_message_reply", "image_message_reply", "card_fallback"):
        logger.record("outbox_delivery", correlation_id=event_keys[scenario], event_key=event_keys[scenario], success=True)
    logger.record("webhook_duplicate", correlation_id=event_keys["duplicate_callback"], event_key=event_keys["duplicate_callback"])
    jobs_path.write_text(
        "\n".join(
            json.dumps({
                "id": f"job_{scenario}",
                "kind": "feishu_message",
                "status": "succeeded",
                "payload": {"event_key": event_key},
                "result": {"run_id": f"run-{scenario}"},
            })
            for scenario, event_key in event_keys.items()
        )
        + "\n",
        encoding="utf-8",
    )
    events_path.write_text("\n".join(json.dumps({"event_key": event_key}) for event_key in event_keys.values()) + "\n", encoding="utf-8")
    bundle_dir = tmp_path / "bundle"
    manifest = build_smoke_evidence_bundle(
        output_dir=str(bundle_dir),
        smoke_path=str(smoke_path),
        log_path=str(runtime_path),
        job_store_path=str(jobs_path),
        event_store_path=str(events_path),
        runtime_lock_path=str(tmp_path / "yinyo_runtime.lock"),
        profile="local",
        transport="ws",
        live_attestation_id="real-attestation-001",
        feishu_app_id_hash="a" * 64,
        tenant_hash="b" * 64,
        ws_sdk_session_id="session-live-runtime-001",
    )
    verified = verify_smoke_evidence_bundle(str(bundle_dir))

    assert manifest["runtime_verification"]["ok"] is True
    assert manifest["live_provenance"]["ws_sdk_session_id"] == "session-live-runtime-001"
    assert not any("session marker" in blocker for blocker in verified["blockers"])
    assert not any("session mismatch" in blocker for blocker in verified["blockers"])


def test_bundle_accepts_card_fallback_from_immediately_preceding_smoke_probe(tmp_path):
    from yinyo import RuntimeLogger, SmokeEvidenceRecorder, build_smoke_evidence_bundle, verify_smoke_evidence_bundle

    smoke_path = tmp_path / "smoke_evidence.jsonl"
    runtime_path = tmp_path / "runtime.jsonl"
    jobs_path = tmp_path / "runtime_jobs.jsonl"
    events_path = tmp_path / "gateway_events.jsonl"
    recorder = SmokeEvidenceRecorder(str(smoke_path))
    event_keys = {
        "text_message_reply": "evt_probe_text",
        "image_message_reply": "evt_probe_image",
        "card_fallback": "evt_probe_card",
        "duplicate_callback": "evt_probe_dup",
    }
    logger = RuntimeLogger(str(runtime_path))
    logger.record(
        "service_start",
        correlation_id="service",
        profile="local",
        transport="ws",
        workspace=str(tmp_path),
        default_model="deepseek-v4-flash",
        model_timeout_seconds=120,
        model_retry_count=1,
        model_retry_backoff_seconds=0.5,
        ack_deadline_seconds=3.0,
        max_steps=50,
        smoke_mode=True,
        event_store_path=str(events_path),
        job_store_path=str(jobs_path),
        log_path=str(runtime_path),
        smoke_evidence_path=str(smoke_path),
        runtime_lock_path=str(tmp_path / "yinyo_runtime.lock"),
        ws_sdk_session_id="session-live-probe-001",
    )
    recorder.record("card_fallback", "passed", live=True, event_key=event_keys["card_fallback"])
    logger.record(
        "outbox_delivery",
        correlation_id=event_keys["card_fallback"],
        event_key=event_keys["card_fallback"],
        success=True,
        fallback=True,
    )
    logger.record(
        "ws_event_received",
        correlation_id=event_keys["card_fallback"],
        event_key=event_keys["card_fallback"],
        ack_latency_ms=12.5,
        ack_deadline_ms=3000.0,
        ack_within_deadline=True,
    )
    _record_ws_runtime_evidence(
        logger,
        event_keys=[event_keys["text_message_reply"], event_keys["image_message_reply"], event_keys["duplicate_callback"]],
        ws_sdk_session_id="session-live-probe-001",
        service_start_offset_seconds=0,
    )
    for scenario in ("text_message_reply", "image_message_reply", "duplicate_callback"):
        recorder.record(scenario, "passed", live=True, event_key=event_keys[scenario])
    _record_advanced_live_evidence(recorder)
    for scenario in ("text_message_reply", "image_message_reply"):
        logger.record("outbox_delivery", correlation_id=event_keys[scenario], event_key=event_keys[scenario], success=True)
    logger.record("webhook_duplicate", correlation_id=event_keys["duplicate_callback"], event_key=event_keys["duplicate_callback"])
    jobs_path.write_text(
        "\n".join(
            json.dumps({
                "id": f"job_{scenario}",
                "kind": "feishu_message",
                "status": "succeeded",
                "payload": {"event_key": event_key},
                "result": {"run_id": f"run-{scenario}"},
            })
            for scenario, event_key in event_keys.items()
        )
        + "\n",
        encoding="utf-8",
    )
    events_path.write_text("\n".join(json.dumps({"event_key": event_key}) for event_key in event_keys.values()) + "\n", encoding="utf-8")
    bundle_dir = tmp_path / "bundle"
    manifest = build_smoke_evidence_bundle(
        output_dir=str(bundle_dir),
        smoke_path=str(smoke_path),
        log_path=str(runtime_path),
        job_store_path=str(jobs_path),
        event_store_path=str(events_path),
        runtime_lock_path=str(tmp_path / "yinyo_runtime.lock"),
        profile="local",
        transport="ws",
        live_attestation_id="real-attestation-001",
        feishu_app_id_hash="a" * 64,
        tenant_hash="b" * 64,
        ws_sdk_session_id="session-live-probe-001",
    )
    verified = verify_smoke_evidence_bundle(str(bundle_dir))

    assert manifest["runtime_verification"]["ok"] is True
    assert manifest["chain"]["session"]["allowed_probe_scenarios"] == ["card_fallback"]
    assert manifest["chain"]["session"]["stale_scenarios"] == []
    assert "bundle ws runtime service_start smoke_mode must be false" not in verified["blockers"]
    assert "smoke_session:stale:card_fallback" not in verified["blockers"]


def test_bundle_verifier_rejects_ws_session_provenance_runtime_mismatch(tmp_path):
    from yinyo import RuntimeLogger, SmokeEvidenceRecorder, build_smoke_evidence_bundle, verify_smoke_evidence_bundle

    smoke_path = tmp_path / "smoke_evidence.jsonl"
    runtime_path = tmp_path / "runtime.jsonl"
    jobs_path = tmp_path / "runtime_jobs.jsonl"
    events_path = tmp_path / "gateway_events.jsonl"
    recorder = SmokeEvidenceRecorder(str(smoke_path))
    event_keys = {
        "text_message_reply": "evt_session_mismatch_text",
        "image_message_reply": "evt_session_mismatch_image",
        "card_fallback": "evt_session_mismatch_card",
        "duplicate_callback": "evt_session_mismatch_dup",
    }
    for scenario, event_key in event_keys.items():
        recorder.record(scenario, "passed", live=True, event_key=event_key)
    _record_advanced_live_evidence(recorder)
    logger = RuntimeLogger(str(runtime_path))
    _record_ws_runtime_evidence(logger, event_keys=list(event_keys.values()), ws_sdk_session_id="session-live-runtime-001")
    for scenario in ("text_message_reply", "image_message_reply", "card_fallback"):
        logger.record("outbox_delivery", correlation_id=event_keys[scenario], event_key=event_keys[scenario], success=True)
    logger.record("webhook_duplicate", correlation_id=event_keys["duplicate_callback"], event_key=event_keys["duplicate_callback"])
    jobs_path.write_text(
        "\n".join(
            json.dumps({
                "id": f"job_{scenario}",
                "kind": "feishu_message",
                "status": "succeeded",
                "payload": {"event_key": event_key},
                "result": {"run_id": f"run-{scenario}"},
            })
            for scenario, event_key in event_keys.items()
        )
        + "\n",
        encoding="utf-8",
    )
    events_path.write_text("\n".join(json.dumps({"event_key": event_key}) for event_key in event_keys.values()) + "\n", encoding="utf-8")
    bundle_dir = tmp_path / "bundle"
    manifest = build_smoke_evidence_bundle(
        output_dir=str(bundle_dir),
        smoke_path=str(smoke_path),
        log_path=str(runtime_path),
        job_store_path=str(jobs_path),
        event_store_path=str(events_path),
        runtime_lock_path=str(tmp_path / "yinyo_runtime.lock"),
        profile="local",
        transport="ws",
        live_attestation_id="real-attestation-001",
        feishu_app_id_hash="a" * 64,
        tenant_hash="b" * 64,
        ws_sdk_session_id="session-live-manifest-002",
    )
    verified = verify_smoke_evidence_bundle(str(bundle_dir))

    assert manifest["runtime_verification"]["ok"] is False
    assert "bundle ws runtime live provenance session mismatch: service_start, ws_transport_start" in manifest["runtime_verification"]["blockers"]
    assert verified["ok"] is False
    assert "bundle ws runtime live provenance session mismatch: service_start, ws_transport_start" in verified["blockers"]


def test_bundle_verifier_rejects_ws_session_provenance_missing_runtime_marker(tmp_path):
    from yinyo import RuntimeLogger, SmokeEvidenceRecorder, build_smoke_evidence_bundle, verify_smoke_evidence_bundle

    smoke_path = tmp_path / "smoke_evidence.jsonl"
    runtime_path = tmp_path / "runtime.jsonl"
    jobs_path = tmp_path / "runtime_jobs.jsonl"
    events_path = tmp_path / "gateway_events.jsonl"
    recorder = SmokeEvidenceRecorder(str(smoke_path))
    event_keys = {
        "text_message_reply": "evt_session_missing_text",
        "image_message_reply": "evt_session_missing_image",
        "card_fallback": "evt_session_missing_card",
        "duplicate_callback": "evt_session_missing_dup",
    }
    for scenario, event_key in event_keys.items():
        recorder.record(scenario, "passed", live=True, event_key=event_key)
    _record_advanced_live_evidence(recorder)
    logger = RuntimeLogger(str(runtime_path))
    _record_ws_runtime_evidence(logger, event_keys=list(event_keys.values()))
    for scenario in ("text_message_reply", "image_message_reply", "card_fallback"):
        logger.record("outbox_delivery", correlation_id=event_keys[scenario], event_key=event_keys[scenario], success=True)
    logger.record("webhook_duplicate", correlation_id=event_keys["duplicate_callback"], event_key=event_keys["duplicate_callback"])
    jobs_path.write_text(
        "\n".join(
            json.dumps({
                "id": f"job_{scenario}",
                "kind": "feishu_message",
                "status": "succeeded",
                "payload": {"event_key": event_key},
                "result": {"run_id": f"run-{scenario}"},
            })
            for scenario, event_key in event_keys.items()
        )
        + "\n",
        encoding="utf-8",
    )
    events_path.write_text("\n".join(json.dumps({"event_key": event_key}) for event_key in event_keys.values()) + "\n", encoding="utf-8")
    bundle_dir = tmp_path / "bundle"
    manifest = build_smoke_evidence_bundle(
        output_dir=str(bundle_dir),
        smoke_path=str(smoke_path),
        log_path=str(runtime_path),
        job_store_path=str(jobs_path),
        event_store_path=str(events_path),
        runtime_lock_path=str(tmp_path / "yinyo_runtime.lock"),
        profile="local",
        transport="ws",
        live_attestation_id="real-attestation-001",
        feishu_app_id_hash="a" * 64,
        tenant_hash="b" * 64,
        ws_sdk_session_id="session-live-manifest-001",
    )
    verified = verify_smoke_evidence_bundle(str(bundle_dir))

    assert manifest["runtime_verification"]["ok"] is False
    assert "bundle ws runtime missing live provenance session marker: service_start, ws_transport_start" in manifest["runtime_verification"]["blockers"]
    assert verified["ok"] is False
    assert "bundle ws runtime missing live provenance session marker: service_start, ws_transport_start" in verified["blockers"]


def test_bundle_verifier_rejects_placeholder_live_provenance_before_candidate(tmp_path):
    from yinyo import SmokeEvidenceRecorder, build_smoke_evidence_bundle, verify_smoke_evidence_bundle

    smoke_path = tmp_path / "smoke_evidence.jsonl"
    runtime_path = tmp_path / "runtime.jsonl"
    jobs_path = tmp_path / "runtime_jobs.jsonl"
    events_path = tmp_path / "gateway_events.jsonl"
    recorder = SmokeEvidenceRecorder(str(smoke_path))
    for scenario in ["url_verification", "text_message_reply", "image_message_reply", "card_fallback", "duplicate_callback"]:
        recorder.record(scenario, "passed", live=True, event_key="evt_provenance")
    _record_advanced_live_evidence(recorder)
    runtime_path.write_text(
        "\n".join([
            json.dumps({"event": "webhook_accepted", "correlation_id": "evt_provenance", "event_key": "evt_provenance"}),
            json.dumps({"event": "outbox_delivery", "correlation_id": "evt_provenance", "event_key": "evt_provenance", "success": True}),
            json.dumps({"event": "webhook_duplicate", "correlation_id": "evt_provenance", "event_key": "evt_provenance"}),
        ])
        + "\n",
        encoding="utf-8",
    )
    jobs_path.write_text(
        json.dumps({"id": "job_1", "kind": "feishu_message", "status": "succeeded", "payload": {"event_key": "evt_provenance"}, "result": {"run_id": "run-provenance"}}) + "\n",
        encoding="utf-8",
    )
    events_path.write_text(json.dumps({"event_key": "evt_provenance"}) + "\n", encoding="utf-8")
    bundle_dir = tmp_path / "bundle"
    build_smoke_evidence_bundle(
        output_dir=str(bundle_dir),
        smoke_path=str(smoke_path),
        log_path=str(runtime_path),
        job_store_path=str(jobs_path),
        event_store_path=str(events_path),
        runtime_lock_path=str(tmp_path / "yinyo_runtime.lock"),
        profile="local",
        transport="http",
        live_attestation_id="real-attestation-001",
        feishu_app_id_hash="redacted-app",
        tenant_hash="test-tenant",
    )

    verified = verify_smoke_evidence_bundle(str(bundle_dir))

    assert verified["ok"] is False
    assert "bundle rejects placeholder live provenance fields: feishu_app_id_hash, tenant_hash" in verified["blockers"]


def test_bundle_verifier_rejects_live_provenance_verification_manifest_drift(tmp_path):
    from yinyo import SmokeEvidenceRecorder, build_smoke_evidence_bundle, verify_smoke_evidence_bundle

    smoke_path = tmp_path / "smoke_evidence.jsonl"
    runtime_path = tmp_path / "runtime.jsonl"
    jobs_path = tmp_path / "runtime_jobs.jsonl"
    events_path = tmp_path / "gateway_events.jsonl"
    recorder = SmokeEvidenceRecorder(str(smoke_path))
    for scenario in ["url_verification", "text_message_reply", "image_message_reply", "card_fallback", "duplicate_callback"]:
        recorder.record(scenario, "passed", live=True, event_key="evt_provenance_drift")
    _record_advanced_live_evidence(recorder)
    runtime_path.write_text(
        "\n".join([
            json.dumps({"event": "webhook_accepted", "correlation_id": "evt_provenance_drift", "event_key": "evt_provenance_drift"}),
            json.dumps({"event": "outbox_delivery", "correlation_id": "evt_provenance_drift", "event_key": "evt_provenance_drift", "success": True}),
            json.dumps({"event": "webhook_duplicate", "correlation_id": "evt_provenance_drift", "event_key": "evt_provenance_drift"}),
        ])
        + "\n",
        encoding="utf-8",
    )
    jobs_path.write_text(
        json.dumps({"id": "job_1", "kind": "feishu_message", "status": "succeeded", "payload": {"event_key": "evt_provenance_drift"}, "result": {"run_id": "run-provenance-drift"}}) + "\n",
        encoding="utf-8",
    )
    events_path.write_text(json.dumps({"event_key": "evt_provenance_drift"}) + "\n", encoding="utf-8")
    bundle_dir = tmp_path / "bundle"
    build_smoke_evidence_bundle(
        output_dir=str(bundle_dir),
        smoke_path=str(smoke_path),
        log_path=str(runtime_path),
        job_store_path=str(jobs_path),
        event_store_path=str(events_path),
        runtime_lock_path=str(tmp_path / "yinyo_runtime.lock"),
        profile="local",
        transport="http",
        live_attestation_id="real-attestation-001",
        feishu_app_id_hash="a" * 64,
        tenant_hash="b" * 64,
    )
    manifest_path = bundle_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["live_provenance_verification"] = {
        "schema": "yinyo.live_provenance_verification.v1",
        "ok": False,
        "blockers": ["tampered"],
        "complete": False,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    verified = verify_smoke_evidence_bundle(str(bundle_dir))

    assert verified["ok"] is False
    assert verified["manifest"]["live_provenance_verification"]["ok"] is False
    assert "bundle live provenance verification does not match manifest provenance" in verified["blockers"]
    assert "bundle live provenance verification blockers do not match manifest provenance" in verified["blockers"]
    assert "bundle live provenance verification completeness does not match manifest provenance" in verified["blockers"]


def test_cli_smoke_bundle_rejects_placeholder_live_provenance_at_build_time(tmp_path):
    import subprocess
    import sys

    from yinyo import SmokeEvidenceRecorder

    smoke_path = tmp_path / "smoke_evidence.jsonl"
    runtime_path = tmp_path / "runtime.jsonl"
    jobs_path = tmp_path / "runtime_jobs.jsonl"
    events_path = tmp_path / "gateway_events.jsonl"
    recorder = SmokeEvidenceRecorder(str(smoke_path))
    for scenario in ["url_verification", "text_message_reply", "image_message_reply", "card_fallback", "duplicate_callback"]:
        recorder.record(scenario, "passed", live=True, event_key="evt_cli_provenance")
    _record_advanced_live_evidence(recorder)
    runtime_path.write_text(
        "\n".join([
            json.dumps({"event": "webhook_accepted", "correlation_id": "evt_cli_provenance", "event_key": "evt_cli_provenance"}),
            json.dumps({"event": "outbox_delivery", "correlation_id": "evt_cli_provenance", "event_key": "evt_cli_provenance", "success": True}),
            json.dumps({"event": "webhook_duplicate", "correlation_id": "evt_cli_provenance", "event_key": "evt_cli_provenance"}),
        ])
        + "\n",
        encoding="utf-8",
    )
    jobs_path.write_text(
        json.dumps({"id": "job_1", "kind": "feishu_message", "status": "succeeded", "payload": {"event_key": "evt_cli_provenance"}, "result": {"run_id": "run-cli-provenance"}}) + "\n",
        encoding="utf-8",
    )
    events_path.write_text(json.dumps({"event_key": "evt_cli_provenance"}) + "\n", encoding="utf-8")
    output_dir = tmp_path / "bundle"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "smoke",
            "bundle",
            "--workspace",
            str(tmp_path),
            "--transport",
            "http",
            "--output",
            str(output_dir),
            "--live-attestation-id",
            "real-attestation-001",
            "--feishu-app-id-hash",
            "redacted-app",
            "--tenant-hash",
            "test-tenant",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))

    assert result.returncode == 1
    assert "live_provenance_blockers:" in result.stdout
    assert "bundle rejects placeholder live provenance fields: feishu_app_id_hash, tenant_hash" in result.stdout
    assert manifest["ok"] is False
    assert manifest["live_provenance_verification"]["ok"] is False


def test_release_verifier_rejects_ws_bundle_with_smoke_mode_enabled_at_service_start(tmp_path, monkeypatch):
    import subprocess
    import sys

    from yinyo import FeishuRuntimeGateway, JsonlEventStore, JsonlJobQueue, RuntimeLogger, SmokeEvidenceRecorder

    class Session:
        def is_duplicate(self, text, user_id):
            return False

    class Agent:
        session_manager = Session()

        def handle_message(self, user_id, chat_id, text, already_deduped=False, correlation_id=""):
            return {"text": "ok", "files": [{"path": "report.md"}], "run_id": f"run-{correlation_id}"}

    class Adapter:
        agent = Agent()

        def add_reaction(self, message_id):
            return True

        def remove_reaction(self, message_id):
            return True

        def send_message(self, *args, **kwargs):
            return {"success": True, "message_ids": ["om_reply"], "fallback": bool(kwargs.get("files"))}

        def _download_image(self, image_key):
            return image_key

    class VisionAdapter:
        def describe(self, image_path, prompt):
            return {"description": "image description"}

    import yinyo.vision_adapter

    monkeypatch.setattr(yinyo.vision_adapter, "get_vision_adapter", lambda: VisionAdapter())
    gateway = FeishuRuntimeGateway(
        adapter=Adapter(),
        agent=Adapter.agent,
        verify_token="good-token",
        queue=JsonlJobQueue(str(tmp_path / "runtime_jobs.jsonl")),
        event_store=JsonlEventStore(str(tmp_path / "gateway_events.jsonl")),
        logger=RuntimeLogger(str(tmp_path / "runtime.jsonl")),
        smoke_recorder=SmokeEvidenceRecorder(str(tmp_path / "smoke_evidence.jsonl")),
    )
    text_event = {
        "type": "event_callback",
        "uuid": "evt_smoke_mode_text",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": "hello"}),
                "chat_id": "oc_1",
                "message_id": "om_smoke_mode_text",
            },
        },
    }
    image_event = {
        "type": "event_callback",
        "uuid": "evt_smoke_mode_image",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "image",
                "content": json.dumps({"image_key": "img_1"}),
                "chat_id": "oc_1",
                "message_id": "om_smoke_mode_image",
            },
        },
    }
    gateway.handle_event(text_event, async_dispatch=False)
    gateway.handle_event(image_event, async_dispatch=False)
    gateway.handle_event(text_event, async_dispatch=False)
    _record_advanced_live_evidence(gateway.smoke_recorder)
    _record_ws_runtime_evidence(gateway.logger, event_keys=_smoke_event_keys(gateway), smoke_mode=True)
    _write_replayable_handoff(
        tmp_path / "runs" / "run-smoke-mode-live",
        run_id="run-smoke-mode-live",
        correlation_id="evt_smoke_mode_text",
        task="smoke mode handoff",
    )

    bundle_dir = tmp_path / "bundle"
    bundle = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "smoke",
            "bundle",
            "--workspace",
            str(tmp_path),
            "--transport",
            "ws",
            "--handoff-dir",
            str(tmp_path / "runs"),
            "--output",
            str(bundle_dir),
            "--live-attestation-id",
            "real-attestation-001",
            "--feishu-app-id-hash",
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "--tenant-hash",
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "--ws-sdk-session-id",
            "session-live-001",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert bundle.returncode == 1
    assert "smoke_mode must be false" in bundle.stdout

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [sys.executable, "scripts/verify_release.py", "--bundle", str(bundle_dir), "--json"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    data = json.loads(result.stdout)

    assert result.returncode == 1
    assert data["bundle"]["ok"] is False
    assert "bundle ws runtime service_start smoke_mode must be false" in data["bundle"]["blockers"]


def test_release_verifier_rejects_ws_bundle_without_per_scenario_ws_events(tmp_path, monkeypatch):
    import subprocess
    import sys

    from yinyo import FeishuRuntimeGateway, JsonlEventStore, JsonlJobQueue, RuntimeLogger, SmokeEvidenceRecorder

    class Session:
        def is_duplicate(self, text, user_id):
            return False

    class Agent:
        session_manager = Session()

        def handle_message(self, user_id, chat_id, text, already_deduped=False, correlation_id=""):
            return {"text": "ok", "files": [{"path": "report.md"}], "run_id": f"run-{correlation_id}"}

    class Adapter:
        agent = Agent()

        def add_reaction(self, message_id):
            return True

        def remove_reaction(self, message_id):
            return True

        def send_message(self, *args, **kwargs):
            return {"success": True, "message_ids": ["om_reply"], "fallback": bool(kwargs.get("files"))}

        def _download_image(self, image_key):
            return image_key

    class VisionAdapter:
        def describe(self, image_path, prompt):
            return {"description": "image description"}

    import yinyo.vision_adapter

    monkeypatch.setattr(yinyo.vision_adapter, "get_vision_adapter", lambda: VisionAdapter())
    gateway = FeishuRuntimeGateway(
        adapter=Adapter(),
        agent=Adapter.agent,
        verify_token="good-token",
        queue=JsonlJobQueue(str(tmp_path / "runtime_jobs.jsonl")),
        event_store=JsonlEventStore(str(tmp_path / "gateway_events.jsonl")),
        logger=RuntimeLogger(str(tmp_path / "runtime.jsonl")),
        smoke_recorder=SmokeEvidenceRecorder(str(tmp_path / "smoke_evidence.jsonl")),
    )
    text_event = {
        "type": "event_callback",
        "uuid": "evt_ws_per_scenario_text",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": "hello"}),
                "chat_id": "oc_1",
                "message_id": "om_ws_per_scenario_text",
            },
        },
    }
    image_event = {
        "type": "event_callback",
        "uuid": "evt_ws_per_scenario_image",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "image",
                "content": json.dumps({"image_key": "img_1"}),
                "chat_id": "oc_1",
                "message_id": "om_ws_per_scenario_image",
            },
        },
    }
    gateway.handle_event(text_event, async_dispatch=False)
    gateway.handle_event(image_event, async_dispatch=False)
    gateway.handle_event(text_event, async_dispatch=False)
    _record_advanced_live_evidence(gateway.smoke_recorder)
    _record_ws_runtime_evidence(gateway.logger, event_keys=["evt_unrelated_ws"])

    bundle_dir = tmp_path / "bundle"
    bundle = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "smoke",
            "bundle",
            "--workspace",
            str(tmp_path),
            "--transport",
            "ws",
            "--output",
            str(bundle_dir),
            "--live-attestation-id",
            "real-attestation-001",
            "--feishu-app-id-hash",
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "--tenant-hash",
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "--ws-sdk-session-id",
            "session-live-001",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert bundle.returncode == 1
    assert "ws_event_received" in bundle.stdout

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [sys.executable, "scripts/verify_release.py", "--bundle", str(bundle_dir), "--json"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    data = json.loads(result.stdout)

    assert result.returncode == 1
    assert data["bundle"]["ok"] is False
    assert any("bundle ws scenario missing ws_event_received: text_message_reply" in item for item in data["bundle"]["blockers"])
    assert any("ws_event_received:text_message_reply" in item for item in data["bundle"]["blockers"])


def test_release_verifier_rejects_tampered_redacted_bundle(tmp_path, monkeypatch):
    import subprocess
    import sys

    from yinyo import FeishuRuntimeGateway, JsonlEventStore, JsonlJobQueue, RuntimeLogger, SmokeEvidenceRecorder

    class Session:
        def is_duplicate(self, text, user_id):
            return False

    class Agent:
        session_manager = Session()

        def handle_message(self, user_id, chat_id, text, already_deduped=False, correlation_id=""):
            return {"text": "ok", "files": [{"path": "report.md"}], "run_id": f"run-{correlation_id}"}

    class Adapter:
        agent = Agent()

        def add_reaction(self, message_id):
            return True

        def remove_reaction(self, message_id):
            return True

        def send_message(self, *args, **kwargs):
            return {"success": True, "message_ids": ["om_reply"], "fallback": bool(kwargs.get("files"))}

        def _download_image(self, image_key):
            return image_key

    class VisionAdapter:
        def describe(self, image_path, prompt):
            return {"description": "image description"}

    import yinyo.vision_adapter

    monkeypatch.setattr(yinyo.vision_adapter, "get_vision_adapter", lambda: VisionAdapter())
    gateway = FeishuRuntimeGateway(
        adapter=Adapter(),
        agent=Adapter.agent,
        verify_token="good-token",
        queue=JsonlJobQueue(str(tmp_path / "runtime_jobs.jsonl")),
        event_store=JsonlEventStore(str(tmp_path / "gateway_events.jsonl")),
        logger=RuntimeLogger(str(tmp_path / "runtime.jsonl")),
        smoke_recorder=SmokeEvidenceRecorder(str(tmp_path / "smoke_evidence.jsonl")),
    )
    text_event = {
        "type": "event_callback",
        "uuid": "evt_bundle_tamper_text",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": "hello"}),
                "chat_id": "oc_1",
                "message_id": "om_bundle_tamper_text",
            },
        },
    }
    image_event = {
        "type": "event_callback",
        "uuid": "evt_bundle_tamper_image",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "image",
                "content": json.dumps({"image_key": "img_1"}),
                "chat_id": "oc_1",
                "message_id": "om_bundle_tamper_image",
            },
        },
    }
    gateway.handle_event({"type": "url_verification", "token": "good-token", "challenge": "challenge"}, async_dispatch=False)
    gateway.handle_event(text_event, async_dispatch=False)
    gateway.handle_event(image_event, async_dispatch=False)
    gateway.handle_event(text_event, async_dispatch=False)
    _record_advanced_live_evidence(gateway.smoke_recorder)

    bundle_dir = tmp_path / "bundle"
    bundle = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "smoke",
            "bundle",
            "--workspace",
            str(tmp_path),
            "--transport",
            "http",
            "--output",
            str(bundle_dir),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert bundle.returncode == 0
    runtime = bundle_dir / "runtime.redacted.jsonl"
    runtime.write_text(
        "\n".join(line for line in runtime.read_text(encoding="utf-8").splitlines() if "outbox_delivery" not in line) + "\n",
        encoding="utf-8",
    )

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [sys.executable, "scripts/verify_release.py", "--bundle", str(bundle_dir), "--json"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    data = json.loads(result.stdout)

    assert result.returncode == 1
    assert data["bundle"]["redacted_chain_ok"] is False
    assert any("file hash mismatch: runtime_log" in item for item in data["bundle"]["blockers"])
    assert any("redacted chain" in item for item in data["bundle"]["blockers"])


def test_bundle_verifier_rejects_frontier_readiness_drift(tmp_path, monkeypatch):
    import copy

    from yinyo import (
        FeishuRuntimeGateway,
        JsonlEventStore,
        JsonlJobQueue,
        RuntimeLogger,
        SmokeEvidenceRecorder,
        build_smoke_evidence_bundle,
        verify_smoke_evidence_bundle,
    )

    class Session:
        def is_duplicate(self, text, user_id):
            return False

    class Agent:
        session_manager = Session()

        def handle_message(self, user_id, chat_id, text, already_deduped=False, correlation_id=""):
            return {"text": "ok", "files": [{"path": "report.md"}], "run_id": f"run-{correlation_id}"}

    class Adapter:
        agent = Agent()

        def add_reaction(self, message_id):
            return True

        def remove_reaction(self, message_id):
            return True

        def send_message(self, *args, **kwargs):
            return {"success": True, "message_ids": ["om_reply"], "fallback": bool(kwargs.get("files"))}

        def _download_image(self, image_key):
            return image_key

    class VisionAdapter:
        def describe(self, image_path, prompt):
            return {"description": "image description"}

    import yinyo.vision_adapter

    monkeypatch.setattr(yinyo.vision_adapter, "get_vision_adapter", lambda: VisionAdapter())
    gateway = FeishuRuntimeGateway(
        adapter=Adapter(),
        agent=Adapter.agent,
        verify_token="good-token",
        queue=JsonlJobQueue(str(tmp_path / "runtime_jobs.jsonl")),
        event_store=JsonlEventStore(str(tmp_path / "gateway_events.jsonl")),
        logger=RuntimeLogger(str(tmp_path / "runtime.jsonl")),
        smoke_recorder=SmokeEvidenceRecorder(str(tmp_path / "smoke_evidence.jsonl")),
    )
    text_event = {
        "type": "event_callback",
        "uuid": "evt_frontier_text",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": "hello"}),
                "chat_id": "oc_1",
                "message_id": "om_frontier_text",
            },
        },
    }
    image_event = {
        "type": "event_callback",
        "uuid": "evt_frontier_image",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "image",
                "content": json.dumps({"image_key": "img_1"}),
                "chat_id": "oc_1",
                "message_id": "om_frontier_image",
            },
        },
    }
    gateway.handle_event({"type": "url_verification", "token": "good-token", "challenge": "challenge"}, async_dispatch=False)
    gateway.handle_event(text_event, async_dispatch=False)
    gateway.handle_event(image_event, async_dispatch=False)
    gateway.handle_event(text_event, async_dispatch=False)
    _record_advanced_live_evidence(gateway.smoke_recorder)
    _write_replayable_handoff(
        tmp_path / "runs" / "run-frontier",
        run_id="run-frontier",
        correlation_id="evt_frontier_text",
        task="frontier bundle",
    )
    bundle_dir = tmp_path / "bundle"
    build_smoke_evidence_bundle(
        output_dir=str(bundle_dir),
        smoke_path=str(tmp_path / "smoke_evidence.jsonl"),
        log_path=str(tmp_path / "runtime.jsonl"),
        job_store_path=str(tmp_path / "runtime_jobs.jsonl"),
        event_store_path=str(tmp_path / "gateway_events.jsonl"),
        runtime_lock_path=str(tmp_path / "yinyo_runtime.lock"),
        transport="http",
        handoff_dir=str(tmp_path / "runs"),
    )
    manifest_path = bundle_dir / "manifest.json"
    base_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases = [
        (
            lambda manifest: manifest["frontier_readiness"].__setitem__(
                "checks",
                [item for item in manifest["frontier_readiness"]["checks"] if item["name"] != "Adaptive simplification guard"],
            ),
            "bundle frontier readiness checks missing",
        ),
        (
            lambda manifest: manifest["frontier_readiness"].__setitem__("handoff_ready_records", 0),
            "bundle frontier handoff_ready_records mismatch",
        ),
        (
            lambda manifest: (
                manifest["frontier_readiness"].__setitem__("handoff_required", True),
                next(
                    item for item in manifest["frontier_readiness"]["checks"] if item["name"] == "State handoff transfer"
                ).__setitem__("live_ok", False),
            ),
            "bundle frontier handoff live proof mismatch",
        ),
    ]

    for mutate, blocker in cases:
        manifest = copy.deepcopy(base_manifest)
        mutate(manifest)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        verified = verify_smoke_evidence_bundle(str(bundle_dir))

        assert verified["ok"] is False
        assert any(blocker in item for item in verified["blockers"])


def test_release_verifier_rejects_bundle_digest_mismatch(tmp_path, monkeypatch):
    import subprocess
    import sys

    from yinyo import FeishuRuntimeGateway, JsonlEventStore, JsonlJobQueue, RuntimeLogger, SmokeEvidenceRecorder

    class Session:
        def is_duplicate(self, text, user_id):
            return False

    class Agent:
        session_manager = Session()

        def handle_message(self, user_id, chat_id, text, already_deduped=False, correlation_id=""):
            return {"text": "ok", "files": [{"path": "report.md"}], "run_id": f"run-{correlation_id}"}

    class Adapter:
        agent = Agent()

        def add_reaction(self, message_id):
            return True

        def remove_reaction(self, message_id):
            return True

        def send_message(self, *args, **kwargs):
            return {"success": True, "message_ids": ["om_reply"], "fallback": bool(kwargs.get("files"))}

        def _download_image(self, image_key):
            return image_key

    class VisionAdapter:
        def describe(self, image_path, prompt):
            return {"description": "image description"}

    import yinyo.vision_adapter

    monkeypatch.setattr(yinyo.vision_adapter, "get_vision_adapter", lambda: VisionAdapter())
    gateway = FeishuRuntimeGateway(
        adapter=Adapter(),
        agent=Adapter.agent,
        verify_token="good-token",
        queue=JsonlJobQueue(str(tmp_path / "runtime_jobs.jsonl")),
        event_store=JsonlEventStore(str(tmp_path / "gateway_events.jsonl")),
        logger=RuntimeLogger(str(tmp_path / "runtime.jsonl")),
        smoke_recorder=SmokeEvidenceRecorder(str(tmp_path / "smoke_evidence.jsonl")),
    )
    text_event = {
        "type": "event_callback",
        "uuid": "evt_bundle_digest_text",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": "hello"}),
                "chat_id": "oc_1",
                "message_id": "om_bundle_digest_text",
            },
        },
    }
    image_event = {
        "type": "event_callback",
        "uuid": "evt_bundle_digest_image",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "image",
                "content": json.dumps({"image_key": "img_1"}),
                "chat_id": "oc_1",
                "message_id": "om_bundle_digest_image",
            },
        },
    }
    gateway.handle_event({"type": "url_verification", "token": "good-token", "challenge": "challenge"}, async_dispatch=False)
    gateway.handle_event(text_event, async_dispatch=False)
    gateway.handle_event(image_event, async_dispatch=False)
    gateway.handle_event(text_event, async_dispatch=False)
    _record_advanced_live_evidence(gateway.smoke_recorder)

    bundle_dir = tmp_path / "bundle"
    bundle = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "smoke",
            "bundle",
            "--workspace",
            str(tmp_path),
            "--transport",
            "http",
            "--output",
            str(bundle_dir),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert bundle.returncode == 0
    manifest_path = bundle_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["bundle_digest"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [sys.executable, "scripts/verify_release.py", "--bundle", str(bundle_dir), "--json"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    data = json.loads(result.stdout)

    assert result.returncode == 1
    assert data["bundle"]["ok"] is False
    assert "bundle digest mismatch" in data["bundle"]["blockers"]


def test_release_verifier_rejects_incomplete_bundle(tmp_path):
    import subprocess
    import sys

    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    (bundle_dir / "manifest.json").write_text('{"ok": false}\n', encoding="utf-8")

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [sys.executable, "scripts/verify_release.py", "--bundle", str(bundle_dir), "--json"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    data = json.loads(result.stdout)

    assert result.returncode == 1
    assert data["bundle"]["ok"] is False
    assert any("missing bundle file" in item for item in data["bundle"]["blockers"])


def test_release_verifier_scans_nested_bundle_files_for_secrets(tmp_path):
    import subprocess
    import sys

    bundle_dir = tmp_path / "bundle"
    nested_dir = bundle_dir / "review-notes"
    nested_dir.mkdir(parents=True)
    (bundle_dir / "manifest.json").write_text('{"ok": false}\n', encoding="utf-8")
    (nested_dir / "operator.json").write_text(
        '{"api_key":"abcd1234abcd1234"}\n',
        encoding="utf-8",
    )

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [sys.executable, "scripts/verify_release.py", "--bundle", str(bundle_dir), "--json"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    data = json.loads(result.stdout)

    assert result.returncode == 1
    assert any("possible secret in bundle file review-notes/operator.json" in item for item in data["bundle"]["blockers"])


def test_release_verifier_does_not_use_invalid_bundle_for_1_0_gate(tmp_path):
    import subprocess
    import sys

    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    (bundle_dir / "manifest.json").write_text('{"ok": false}\n', encoding="utf-8")

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [
            sys.executable,
            "scripts/verify_release.py",
            "--target",
            "1.0.0",
            "--bundle",
            str(bundle_dir),
            "--json",
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    data = json.loads(result.stdout)
    items = {item["id"]: item for item in data["items"]}

    assert result.returncode == 1
    assert data["bundle"]["ok"] is False
    assert items["R1-03"]["passed"] is False
    assert items["R1-07"]["passed"] is False
    assert any("bundle:" in item for item in data["failures"])


def test_reset_smoke_evidence_files_requires_confirmation(tmp_path):
    from yinyo import reset_smoke_evidence_files

    try:
        reset_smoke_evidence_files(
            smoke_path=str(tmp_path / "smoke.jsonl"),
            log_path=str(tmp_path / "runtime.jsonl"),
            job_store_path=str(tmp_path / "jobs.jsonl"),
            event_store_path=str(tmp_path / "events.jsonl"),
        )
    except ValueError as exc:
        msg = str(exc)
    else:
        raise AssertionError("expected reset confirmation error")

    assert "confirm=True" in msg


def test_reset_smoke_evidence_files_clears_only_evidence_files(tmp_path):
    from yinyo import reset_smoke_evidence_files

    smoke = tmp_path / "smoke.jsonl"
    runtime = tmp_path / "runtime.jsonl"
    jobs = tmp_path / "runtime_jobs.jsonl"
    events = tmp_path / "gateway_events.jsonl"
    keep = tmp_path / "runs" / "manifest.json"
    keep.parent.mkdir()
    for path in (smoke, runtime, jobs, events, keep):
        path.write_text('{"ok": true}\n', encoding="utf-8")

    result = reset_smoke_evidence_files(
        smoke_path=str(smoke),
        log_path=str(runtime),
        job_store_path=str(jobs),
        event_store_path=str(events),
        confirm=True,
    )

    assert result["ok"] is True
    assert smoke.read_text(encoding="utf-8") == ""
    assert runtime.read_text(encoding="utf-8") == ""
    assert jobs.read_text(encoding="utf-8") == ""
    assert events.read_text(encoding="utf-8") == ""
    assert keep.read_text(encoding="utf-8") == '{"ok": true}\n'
    assert result["reset"]["smoke_evidence"]["previous_bytes"] > 0


def test_cli_smoke_reset_requires_confirmation_and_outputs_json(tmp_path):
    import subprocess
    import sys

    config_path = tmp_path / "runtime.env"
    config_path.write_text(f"workspace={tmp_path}\ntransport=http\n", encoding="utf-8")
    for name in ("smoke_evidence.jsonl", "runtime.jsonl", "runtime_jobs.jsonl", "gateway_events.jsonl"):
        (tmp_path / name).write_text('{"old": true}\n', encoding="utf-8")

    refused = subprocess.run(
        [sys.executable, "-m", "yinyo.cli", "smoke", "reset", "--config", str(config_path)],
        text=True,
        capture_output=True,
        check=False,
    )
    accepted = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "smoke",
            "reset",
            "--config",
            str(config_path),
            "--confirm-reset",
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    data = json.loads(accepted.stdout)

    assert refused.returncode == 2
    assert "Reset refused" in refused.stderr
    assert accepted.returncode == 0
    assert data["ok"] is True
    assert data["reset"]["smoke_evidence"]["previous_bytes"] > 0
    assert (tmp_path / "smoke_evidence.jsonl").read_text(encoding="utf-8") == ""


def test_cli_smoke_wait_reports_complete_chain_and_timeout(tmp_path, monkeypatch):
    import subprocess
    import sys

    from yinyo import FeishuRuntimeGateway, JsonlEventStore, JsonlJobQueue, RuntimeLogger, SmokeEvidenceRecorder

    class Session:
        def is_duplicate(self, text, user_id):
            return False

    class Agent:
        session_manager = Session()

        def handle_message(self, user_id, chat_id, text, already_deduped=False, correlation_id=""):
            return {"text": "ok", "files": [{"path": "report.md"}], "run_id": f"run-{correlation_id}"}

    class Adapter:
        agent = Agent()

        def add_reaction(self, message_id):
            return True

        def remove_reaction(self, message_id):
            return True

        def send_message(self, *args, **kwargs):
            return {"success": True, "message_ids": ["om_reply"], "fallback": bool(kwargs.get("files"))}

        def _download_image(self, image_key):
            return image_key

    class VisionAdapter:
        def describe(self, image_path, prompt):
            return {"description": "image description"}

    import yinyo.vision_adapter

    monkeypatch.setattr(yinyo.vision_adapter, "get_vision_adapter", lambda: VisionAdapter())
    gateway = FeishuRuntimeGateway(
        adapter=Adapter(),
        agent=Adapter.agent,
        verify_token="good-token",
        queue=JsonlJobQueue(str(tmp_path / "runtime_jobs.jsonl")),
        event_store=JsonlEventStore(str(tmp_path / "gateway_events.jsonl")),
        logger=RuntimeLogger(str(tmp_path / "runtime.jsonl")),
        smoke_recorder=SmokeEvidenceRecorder(str(tmp_path / "smoke_evidence.jsonl")),
    )
    text_event = {
        "type": "event_callback",
        "uuid": "evt_wait_text",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": "hello"}),
                "chat_id": "oc_1",
                "message_id": "om_wait_text",
            },
        },
    }
    image_event = {
        "type": "event_callback",
        "uuid": "evt_wait_image",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "image",
                "content": json.dumps({"image_key": "img_1"}),
                "chat_id": "oc_1",
                "message_id": "om_wait_image",
            },
        },
    }
    gateway.handle_event({"type": "url_verification", "token": "good-token", "challenge": "challenge"}, async_dispatch=False)
    gateway.handle_event(text_event, async_dispatch=False)
    gateway.handle_event(image_event, async_dispatch=False)
    gateway.handle_event(text_event, async_dispatch=False)

    config_path = tmp_path / "runtime.env"
    config_path.write_text(f"workspace={tmp_path}\ntransport=http\n", encoding="utf-8")
    ok = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "smoke",
            "wait",
            "--config",
            str(config_path),
            "--timeout",
            "0",
            "--interval",
            "0.1",
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    ok_data = json.loads(ok.stdout)

    assert ok.returncode == 1
    assert ok_data["ok"] is False
    assert ok_data["chain"]["chain_ok"] is True
    assert ok_data["chain"]["advanced_ok"] is False
    assert "advanced:trace2skill_promotion" in ok_data["chain"]["missing"]

    _record_advanced_live_evidence(gateway.smoke_recorder)
    complete = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "smoke",
            "wait",
            "--config",
            str(config_path),
            "--timeout",
            "0",
            "--interval",
            "0.1",
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    complete_data = json.loads(complete.stdout)

    assert complete.returncode == 0
    assert complete_data["ok"] is True
    assert complete_data["chain"]["missing"] == []

    empty = tmp_path / "empty"
    empty.mkdir()
    timeout = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "smoke",
            "wait",
            "--workspace",
            str(empty),
            "--timeout",
            "0",
            "--interval",
            "0.1",
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    timeout_data = json.loads(timeout.stdout)

    assert timeout.returncode == 1
    assert timeout_data["timed_out"] is True
    assert "smoke:text_message_reply" in timeout_data["chain"]["missing"]
    assert timeout_data["operator_next_actions"]
    assert any("Send a plain text message" in item for item in timeout_data["operator_next_actions"])
    assert any(item["scenario"] == "text_message_reply" for item in timeout_data["operator_plan"])
    assert timeout_data["handoff_summary"]["ready_to_handoff"] is True
    assert "basic" in timeout_data["handoff_summary"]["blocking_layers"]


def test_feishu_scenario_fixtures_replay_successfully():
    import os
    import subprocess
    import sys

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [sys.executable, "scripts/replay_scenarios.py"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert '"passed": true' in result.stdout


def test_replay_scenarios_api_reports_all_passed():
    import os
    from yinyo import replay_release_matrix, replay_scenarios

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    results = replay_scenarios(os.path.join(repo, "examples", "feishu_scenarios.json"))
    matrix = replay_release_matrix(os.path.join(repo, "examples", "feishu_scenarios.json"))

    assert results
    assert all(item["passed"] for item in results)
    assert matrix["corpus"]["schema"] == "yinyo.harness_corpus_metadata.v1"
    assert len(matrix["corpus"]["sha256"]) == 64
    assert matrix["corpus"]["package_root_match"] is True
    assert matrix["corpus"]["active_matches_package"] is True
    assert matrix["corpus"]["active_matches_root"] is True
    assert any(item["name"] == "duplicate_text" and item["duplicate"] for item in results)
    assert any(item["name"] == "image_understanding" for item in results)
    for item in results:
        envelope = item.get("proof_envelope", {})
        assert envelope["schema"] == "yinyo.proof_envelope.v1"
        assert envelope["source"]
        assert envelope["refs"]
        assert len(envelope["digest"]) == 64
    assert matrix["ok"] is True
    assert all(row["passed"] for row in matrix["matrix"]["rows"])
    assert matrix["matrix"]["scope"] == "local_harness_evidence"
    assert matrix["matrix"]["live_product_required_for_1_0"] is True
    assert matrix["matrix"]["harness_layers"]["schema"] == "yinyo.harness_layers.v1"
    assert matrix["matrix"]["harness_layers"]["framework"] == "ETCLOVG"
    assert matrix["matrix"]["harness_layers"]["source"] == "https://picrew.github.io/LLM-Harness/"
    assert matrix["matrix"]["harness_layers"]["missing_layers"] == []
    execution = next(row for row in matrix["matrix"]["harness_layers"]["rows"] if row["layer"] == "Execution")
    assert "ack_boundary" in execution["required_proof"]
    assert "worker_saturation" in execution["required_proof"]
    assert "workspace_boundary" in execution["required_proof"]
    assert "resource_quota" in execution["required_proof"]
    governance = next(row for row in matrix["matrix"]["harness_layers"]["rows"] if row["layer"] == "Governance")
    assert "runtime_lock" in governance["required_proof"]
    assert "workspace_boundary" in governance["required_proof"]
    assert "resource_quota" in governance["required_proof"]
    context = next(row for row in matrix["matrix"]["harness_layers"]["rows"] if row["layer"] == "Context")
    assert "temporal_state_recovery" in context["required_proof"]
    assert set(matrix["matrix"]["harness_layers"]["passed_layers"]) == {
        "Execution",
        "Tooling",
        "Context",
        "Lifecycle",
        "Observability",
        "Verification",
        "Governance",
    }
    assert all(row["local_harness_passed"] for row in matrix["matrix"]["rows"])
    assert all(row["live_product_required"] for row in matrix["matrix"]["rows"])
    assert all(row["required_proof"] for row in matrix["matrix"]["rows"])
    assert all(row["provided_proof"] for row in matrix["matrix"]["rows"])
    assert not any(row["missing_proof"] for row in matrix["matrix"]["rows"])
    assert not any(row["missing_required_proof"] for row in matrix["matrix"]["rows"])
    assert matrix["matrix"]["proof_status"]["text_reply"]["proof"] == ["gateway_job"]
    assert matrix["matrix"]["proof_status"]["ack_boundary"]["proof"] == ["ack_boundary"]
    assert matrix["matrix"]["proof_status"]["ws_sdk_envelope_normalization"]["proof"] == ["ws_sdk_envelope"]
    assert matrix["matrix"]["proof_status"]["worker_saturation_backpressure"]["proof"] == ["worker_saturation"]
    assert matrix["matrix"]["proof_status"]["runtime_lock_single_writer"]["proof"] == ["runtime_lock"]
    assert matrix["matrix"]["proof_status"]["workspace_boundary"]["proof"] == ["workspace_boundary"]
    assert matrix["matrix"]["proof_status"]["resource_quota"]["proof"] == ["resource_quota"]
    assert matrix["matrix"]["proof_status"]["temporal_state_recovery"]["proof"] == ["temporal_state_recovery"]
    assert matrix["matrix"]["proof_status"]["trace_failure_diagnosis"]["proof"] == ["trace_failure_diagnosis"]
    assert matrix["matrix"]["proof_status"]["adaptive_simplification"]["proof"] == ["adaptive_simplification"]


def test_release_matrix_product_rows_require_declared_proofs():
    from yinyo.release_matrix import _evaluate_release_matrix_from_proof_status

    proof_by_name = {
        "text_reply": {"passed": True, "proof": [], "missing": []},
        "duplicate_text": {"passed": True, "proof": [], "missing": []},
        "ws_sdk_envelope_normalization": {"passed": True, "proof": [], "missing": []},
    }

    matrix = _evaluate_release_matrix_from_proof_status(proof_by_name)
    row = next(item for item in matrix["rows"] if item["id"] == "core.less_is_more")

    assert matrix["ok"] is False
    assert row["local_harness_passed"] is False
    assert row["passed"] is False
    assert set(row["missing_required_proof"]) == {"gateway_job", "duplicate_guard", "ws_sdk_envelope"}
    assert set(row["missing_required_proof"]).issubset(set(row["missing_proof"]))


def test_release_matrix_advanced_scenarios_include_executable_evidence():
    import os
    from yinyo import replay_scenarios

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    by_name = {
        item["name"]: item
        for item in replay_scenarios(os.path.join(repo, "examples", "feishu_scenarios.json"))
    }

    assert by_name["long_conversation"]["evidence"]["masked_observations_after"] > 0
    assert by_name["text_reply"]["gateway"]["job_status"] == "succeeded"
    assert by_name["text_reply"]["gateway"]["delivery"] is True
    assert by_name["text_reply"]["run"]["correlation_id"] == by_name["text_reply"]["gateway"]["event_key"]
    assert by_name["duplicate_text"]["gateway"]["duplicate"] is True
    assert by_name["duplicate_text"]["gateway"]["job_id"] == ""
    assert by_name["duplicate_text"]["gateway"]["delivery"] is False
    assert by_name["image_understanding"]["evidence"]["agent_text_contains_description"] is True
    assert by_name["image_understanding"]["gateway"]["job_status"] == "succeeded"
    assert by_name["memory_supersession"]["evidence"]["audit_trail_length"] == 2
    assert by_name["memory_durability_policy"]["evidence"]["stored"] == 1
    assert by_name["memory_durability_policy"]["evidence"]["rejected"] == 1
    assert by_name["memory_durability_policy"]["evidence"]["active_categories"] == ["Preferences"]
    assert by_name["temporal_state_recovery"]["evidence"]["state_report_schema"] == "yinyo.temporal_state_report.v1"
    assert by_name["temporal_state_recovery"]["evidence"]["recovered_from_disk"] is True
    assert by_name["temporal_state_recovery"]["evidence"]["provenance_complete"] is True
    assert by_name["temporal_state_recovery"]["evidence"]["stale"] == 0
    assert by_name["adaptive_simplification"]["evidence"]["ablation_schema"] == "yinyo.proof_ablation.v1"
    assert by_name["adaptive_simplification"]["evidence"]["target_proof"] == "model_usage"
    assert by_name["adaptive_simplification"]["evidence"]["baseline_ok"] is True
    assert by_name["adaptive_simplification"]["evidence"]["proof_ablated_ok"] is False
    assert by_name["adaptive_simplification"]["evidence"]["scenario_ablated_ok"] is False
    assert by_name["adaptive_simplification"]["evidence"]["missing_proof_detected"] is True
    assert {"Observability", "Verification"}.issubset(set(by_name["adaptive_simplification"]["evidence"]["affected_layers"]))
    assert "core.deepseek_adapted" in by_name["adaptive_simplification"]["evidence"]["affected_rows"]
    assert by_name["fact_hygiene_policy"]["evidence"]["status"] == "source_required"
    assert by_name["trace2skill_promotion"]["evidence"]["promotion_status"] in {"proven", "stable"}
    assert by_name["trace2skill_promotion"]["evidence"]["regression_replay_passed"] is True
    assert by_name["trace2skill_promotion"]["evidence"]["validation_passed"] is True
    assert by_name["trace2skill_promotion"]["evidence"]["replay_command_passed"] is True
    assert by_name["trace2skill_promotion"]["evidence"]["pre_skill_failure_reproduced"] is True
    assert by_name["trace2skill_promotion"]["evidence"]["post_skill_guardrail_applied"] is True
    assert by_name["trace2skill_promotion"]["evidence"]["guardrail_applied"] is True
    assert by_name["trace2skill_promotion"]["evidence"]["pre_skill_failed"] is True
    assert by_name["trace2skill_promotion"]["evidence"]["pre_skill_exit_code"] != 0
    assert by_name["trace2skill_promotion"]["evidence"]["pre_skill_run_ref"].endswith(".json")
    assert by_name["trace2skill_promotion"]["evidence"]["post_skill_passed"] is True
    assert by_name["trace2skill_promotion"]["evidence"]["post_skill_exit_code"] == 0
    assert by_name["trace2skill_promotion"]["evidence"]["post_skill_run_ref"].endswith(".json")
    assert by_name["trace2skill_promotion"]["evidence"]["pre_skill_run_ref"] != by_name["trace2skill_promotion"]["evidence"]["post_skill_run_ref"]
    assert by_name["trace2skill_promotion"]["evidence"]["replay_exit_code"] == 0
    assert by_name["trace2skill_promotion"]["evidence"]["replay_stdout_mentions_failure"] is True
    assert by_name["trace2skill_promotion"]["evidence"]["replay_stdout_mentions_guardrail"] is True
    assert by_name["trace2skill_promotion"]["evidence"]["promotion_record"] is True
    assert by_name["trace2skill_promotion"]["evidence"]["failure_trace_ref"].startswith("trace2skill:")
    assert by_name["trace2skill_promotion"]["evidence"]["post_promotion_run_ref"].endswith(".json")
    assert by_name["trace2skill_promotion"]["evidence"]["post_promotion_run_ref"] == by_name["trace2skill_promotion"]["evidence"]["post_skill_run_ref"]
    assert by_name["ack_boundary"]["evidence"]["schema"] == "yinyo.ack_boundary.v1"
    assert by_name["ack_boundary"]["evidence"]["ack_before_agent_execution"] is True
    assert by_name["ack_boundary"]["evidence"]["async_dispatch_requested"] is True
    assert by_name["ack_boundary"]["evidence"]["post_ack_handler_executed"] is True
    assert by_name["ack_boundary"]["evidence"]["ack_latency_ms"] <= by_name["ack_boundary"]["evidence"]["ack_deadline_ms"]
    assert by_name["ack_boundary"]["gateway"]["job_status_at_ack"] == "queued"
    assert by_name["ack_boundary"]["gateway"]["post_ack_job_status"] == "succeeded"
    assert by_name["ws_sdk_envelope_normalization"]["evidence"]["schema"] == "yinyo.ws_sdk_envelope_normalization.v1"
    assert by_name["ws_sdk_envelope_normalization"]["evidence"]["sdk_schema"] == "2.0"
    assert by_name["ws_sdk_envelope_normalization"]["evidence"]["header_event_id"] == "evt_ws_sdk_1"
    assert by_name["ws_sdk_envelope_normalization"]["evidence"]["normalized_uuid"] == "evt_ws_sdk_1"
    assert by_name["ws_sdk_envelope_normalization"]["evidence"]["normalized_message_type"] == "text"
    assert by_name["ws_sdk_envelope_normalization"]["evidence"]["normalized_text"] == "hello from sdk"
    assert by_name["ws_sdk_envelope_normalization"]["evidence"]["gateway_received_normalized"] is True
    assert by_name["ws_sdk_envelope_normalization"]["evidence"]["logger_recorded_ws_event"] is True
    assert by_name["ws_sdk_envelope_normalization"]["gateway"]["job_status_at_ack"] == "queued"
    assert by_name["worker_saturation_backpressure"]["evidence"]["schema"] == "yinyo.worker_saturation.v1"
    assert by_name["worker_saturation_backpressure"]["evidence"]["rejected_jobs"] == 1
    assert by_name["worker_saturation_backpressure"]["evidence"]["rejection_recorded"] is True
    assert by_name["runtime_lock_single_writer"]["evidence"]["schema"] == "yinyo.runtime_lock_single_writer.v1"
    assert by_name["runtime_lock_single_writer"]["evidence"]["second_writer_blocked"] is True
    assert by_name["runtime_lock_single_writer"]["evidence"]["available_after_release"] is True
    assert by_name["workspace_boundary"]["evidence"]["schema"] == "yinyo.workspace_boundary.v1"
    assert by_name["workspace_boundary"]["evidence"]["inside_read_ok"] is True
    assert by_name["workspace_boundary"]["evidence"]["blocked_operations"] == 5
    assert by_name["workspace_boundary"]["evidence"]["escaped_file_created"] is False
    assert by_name["resource_quota"]["evidence"]["schema"] == "yinyo.resource_quota.v1"
    assert by_name["resource_quota"]["evidence"]["read_shown"] == by_name["resource_quota"]["evidence"]["read_limit"]
    assert by_name["resource_quota"]["evidence"]["search_returned"] == 50
    assert by_name["resource_quota"]["evidence"]["large_file_skipped"] is True
    assert by_name["resource_quota"]["evidence"]["stdout_chars"] <= by_name["resource_quota"]["evidence"]["stdout_limit"]
    assert by_name["resource_quota"]["evidence"]["stderr_chars"] <= by_name["resource_quota"]["evidence"]["stderr_limit"]
    assert by_name["resource_quota"]["evidence"]["timeout_blocked"] is True
    assert by_name["delegated_worker_trace"]["evidence"]["schema"] == "yinyo.delegated_worker_trace.v1"
    assert by_name["delegated_worker_trace"]["evidence"]["parent_context_shared"] is True
    assert by_name["delegated_worker_trace"]["evidence"]["worker_status"] == "success"
    assert by_name["delegated_worker_trace"]["evidence"]["worker_run_id"].startswith("sub-")
    assert by_name["delegated_worker_trace"]["evidence"]["worker_run_id"] != by_name["delegated_worker_trace"]["evidence"]["parent_run_id"]
    assert by_name["delegated_worker_trace"]["evidence"]["tool_traces_count"] >= 1
    assert "do_search" in by_name["delegated_worker_trace"]["evidence"]["tool_names"]
    assert by_name["delegated_worker_trace"]["evidence"]["trace_refs"]
    assert by_name["trace_failure_diagnosis"]["evidence"]["diagnosis_schema"] == "yinyo.trace_failure_diagnosis.v1"
    assert by_name["trace_failure_diagnosis"]["evidence"]["root_cause"] == "runtime_job_failed"
    assert by_name["trace_failure_diagnosis"]["evidence"]["trace_complete"] is True
    assert by_name["deepseek_usage"]["evidence"]["model_usage"]["total_tokens"] > 0
    assert by_name["deepseek_usage"]["evidence"]["manifest_matches_result"] is True
    envelope = by_name["deepseek_usage"]["evidence"]["model_envelope"]
    assert envelope["schema"] == "yinyo.model_envelope.v1"
    assert envelope["within_budget"] is True
    assert envelope["retry_recovered"] is True
    assert envelope["fallback_observed"] is True
    assert envelope["degradation_status"] == "model_error"
    assert {"timeout", "rate_limit"}.issubset(set(envelope["error_classifications"]))
    assert by_name["card_fallback"]["evidence"]["gateway_fallback"] is True
    assert {"text_message_reply", "card_fallback"}.issubset(set(by_name["card_fallback"]["evidence"]["smoke_passed"]))
    assert by_name["card_fallback"]["gateway"]["fallback"] is True
    assert by_name["partial_failure"]["evidence"]["blocked_evidence_records"] > 0
    assert by_name["partial_failure"]["evidence"]["no_false_success"] is True
    assert by_name["release_gate"]["evidence"]["missing_live_scenarios"]
    assert by_name["release_gate"]["evidence"]["transport"] == "ws"
    assert "url_verification" not in by_name["release_gate"]["evidence"]["required_live_scenarios"]
    assert by_name["release_gate"]["bundle"]["required"] is True
    assert by_name["release_gate"]["bundle"]["verified"] is False
    for name in (
        "image_understanding",
        "long_conversation",
        "memory_supersession",
        "memory_durability_policy",
        "trace2skill_promotion",
        "ack_boundary",
        "ws_sdk_envelope_normalization",
        "worker_saturation_backpressure",
        "runtime_lock_single_writer",
        "resource_quota",
        "state_handoff",
        "delegated_worker_trace",
        "deepseek_usage",
        "partial_failure",
        "release_gate",
    ):
        assert by_name[name]["corpus_id"] == name
        assert by_name[name]["corpus_version"] == "1.0.0"
        assert by_name[name]["runner"] == name
        assert by_name[name]["proof_contract"]["schema"] == "yinyo.proof_contract.v1"
        assert by_name[name]["proof_envelope"]["source"] == "versioned_harness_corpus"


def test_harness_corpus_expectations_can_fail_replay(tmp_path):
    import os
    from pathlib import Path

    from yinyo import replay_release_matrix

    repo = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    corpus = json.loads((repo / "corpus" / "harness" / "scenarios.v1.json").read_text(encoding="utf-8"))
    for case in corpus["cases"]:
        if case["id"] == "long_conversation":
            case["expect"]["evidence"]["masked_observations_after"]["value"] = 9999
    failing_corpus = tmp_path / "scenarios.v1.json"
    failing_corpus.write_text(json.dumps(corpus, ensure_ascii=False), encoding="utf-8")

    matrix = replay_release_matrix(repo / "examples" / "feishu_scenarios.json", harness_corpus_path=failing_corpus)
    long_context = next(item for item in matrix["scenarios"] if item["name"] == "long_conversation")

    assert matrix["ok"] is False
    assert long_context["passed"] is False
    assert any(row["id"] == "trait.multidisciplinary" and not row["passed"] for row in matrix["matrix"]["rows"])


def test_harness_corpus_ack_boundary_expectations_can_fail_execution_layer(tmp_path):
    import os
    from pathlib import Path

    from yinyo import replay_release_matrix

    repo = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    corpus = json.loads((repo / "corpus" / "harness" / "scenarios.v1.json").read_text(encoding="utf-8"))
    for case in corpus["cases"]:
        if case["id"] == "ack_boundary":
            case["expect"]["gateway"]["job_status_at_ack"] = "succeeded"
    failing_corpus = tmp_path / "scenarios.v1.json"
    failing_corpus.write_text(json.dumps(corpus, ensure_ascii=False), encoding="utf-8")

    matrix = replay_release_matrix(repo / "examples" / "feishu_scenarios.json", harness_corpus_path=failing_corpus)
    ack_boundary = next(item for item in matrix["scenarios"] if item["name"] == "ack_boundary")

    assert matrix["ok"] is False
    assert ack_boundary["passed"] is False
    assert matrix["matrix"]["proof_status"]["ack_boundary"]["passed"] is False
    execution = next(row for row in matrix["matrix"]["harness_layers"]["rows"] if row["layer"] == "Execution")
    assert "ack_boundary" in execution["missing_proof"]


def test_harness_corpus_ws_sdk_envelope_expectations_can_fail_execution_layer(tmp_path):
    import os
    from pathlib import Path

    from yinyo import replay_release_matrix

    repo = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    corpus = json.loads((repo / "corpus" / "harness" / "scenarios.v1.json").read_text(encoding="utf-8"))
    for case in corpus["cases"]:
        if case["id"] == "ws_sdk_envelope_normalization":
            case["expect"]["evidence"]["normalized_text"] = "wrong text"
    failing_corpus = tmp_path / "scenarios.v1.json"
    failing_corpus.write_text(json.dumps(corpus, ensure_ascii=False), encoding="utf-8")

    matrix = replay_release_matrix(repo / "examples" / "feishu_scenarios.json", harness_corpus_path=failing_corpus)
    ws_sdk = next(item for item in matrix["scenarios"] if item["name"] == "ws_sdk_envelope_normalization")

    assert matrix["ok"] is False
    assert ws_sdk["passed"] is False
    assert matrix["matrix"]["proof_status"]["ws_sdk_envelope_normalization"]["passed"] is False
    execution = next(row for row in matrix["matrix"]["harness_layers"]["rows"] if row["layer"] == "Execution")
    verification = next(row for row in matrix["matrix"]["harness_layers"]["rows"] if row["layer"] == "Verification")
    assert "ws_sdk_envelope" in execution["missing_proof"]
    assert "ws_sdk_envelope" in verification["missing_proof"]


def test_harness_corpus_delegated_worker_trace_expectations_can_fail_tooling_layer(tmp_path):
    import os
    from pathlib import Path

    from yinyo import replay_release_matrix

    repo = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    corpus = json.loads((repo / "corpus" / "harness" / "scenarios.v1.json").read_text(encoding="utf-8"))
    for case in corpus["cases"]:
        if case["id"] == "delegated_worker_trace":
            case["expect"]["evidence"]["required_tool"] = "do_read"
    failing_corpus = tmp_path / "scenarios.v1.json"
    failing_corpus.write_text(json.dumps(corpus, ensure_ascii=False), encoding="utf-8")

    matrix = replay_release_matrix(repo / "examples" / "feishu_scenarios.json", harness_corpus_path=failing_corpus)
    delegated = next(item for item in matrix["scenarios"] if item["name"] == "delegated_worker_trace")

    assert matrix["ok"] is False
    assert delegated["passed"] is False
    assert matrix["matrix"]["proof_status"]["delegated_worker_trace"]["passed"] is False
    tooling = next(row for row in matrix["matrix"]["harness_layers"]["rows"] if row["layer"] == "Tooling")
    lifecycle = next(row for row in matrix["matrix"]["harness_layers"]["rows"] if row["layer"] == "Lifecycle")
    assert "delegated_worker_trace" in tooling["missing_proof"]
    assert "delegated_worker_trace" in lifecycle["missing_proof"]


def test_harness_corpus_contract_rejects_unknown_refs(tmp_path):
    import os
    from pathlib import Path

    from yinyo import validate_harness_corpus_contract

    repo = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    corpus = json.loads((repo / "corpus" / "harness" / "scenarios.v1.json").read_text(encoding="utf-8"))
    corpus["cases"][0]["release_matrix_refs"] = ["trait.unknown"]
    corpus["cases"][0]["proof_required"] = ["unknown_proof"]
    corpus["cases"][0]["live_scenario"] = "unknown_live"
    failing_corpus = tmp_path / "scenarios.v1.json"
    failing_corpus.write_text(json.dumps(corpus, ensure_ascii=False), encoding="utf-8")

    result = validate_harness_corpus_contract(failing_corpus)

    assert result["ok"] is False
    assert any("release_matrix_ref_unknown:trait.unknown" in item for item in result["errors"])
    assert any("proof_required_unknown:unknown_proof" in item for item in result["errors"])
    assert any("live_scenario_not_in_release_matrix:unknown_live" in item for item in result["errors"])


def test_harness_corpus_contract_rejects_missing_state_handoff_case(tmp_path):
    import os
    from pathlib import Path

    from yinyo import validate_harness_corpus_contract

    repo = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    corpus = json.loads((repo / "corpus" / "harness" / "scenarios.v1.json").read_text(encoding="utf-8"))
    corpus["cases"] = [case for case in corpus["cases"] if case["id"] != "state_handoff"]
    failing_corpus = tmp_path / "scenarios.v1.json"
    failing_corpus.write_text(json.dumps(corpus, ensure_ascii=False), encoding="utf-8")

    result = validate_harness_corpus_contract(failing_corpus)

    assert result["ok"] is False
    assert "state_handoff:case_missing" in result["errors"]


def test_release_matrix_rejects_passed_scenarios_without_trace_proof():
    from yinyo.release_matrix import RELEASE_MATRIX, evaluate_release_matrix

    weak_results = [
        {"name": name, "passed": True}
        for requirement in RELEASE_MATRIX
        for name in requirement.required_scenarios
    ]
    matrix = evaluate_release_matrix(weak_results)

    assert matrix["ok"] is False
    assert all(row["missing_proof"] for row in matrix["rows"])
    assert matrix["passed_scenarios"] == []


def test_release_matrix_rejects_trace2skill_blind_ok_only():
    import copy
    import os
    from yinyo import build_proof_envelope, replay_scenarios
    from yinyo.release_matrix import evaluate_release_matrix

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    results = copy.deepcopy(replay_scenarios(os.path.join(repo, "examples", "feishu_scenarios.json")))
    target = next(item for item in results if item["name"] == "trace2skill_promotion")
    target["evidence"] = {
        "regression_fixture": True,
        "blind_test_passed": True,
        "promotion_status": "proven",
        "activation_count": 5,
    }
    target["proof_envelope"] = build_proof_envelope(
        item=target,
        source="trace2skill_fixture",
        refs={"post_promotion_run_ref": "blind-ok"},
    )

    matrix = evaluate_release_matrix(results)

    assert matrix["proof_status"]["trace2skill_promotion"]["missing"]


def test_release_matrix_rejects_invalid_proof_envelopes():
    import copy
    import os
    from yinyo import replay_scenarios
    from yinyo.release_matrix import evaluate_release_matrix

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    base = replay_scenarios(os.path.join(repo, "examples", "feishu_scenarios.json"))
    target_index = next(i for i, item in enumerate(base) if item["name"] == "text_reply")
    cases = []
    no_envelope = copy.deepcopy(base)
    no_envelope[target_index].pop("proof_envelope")
    cases.append(no_envelope)
    bad_schema = copy.deepcopy(base)
    bad_schema[target_index]["proof_envelope"]["schema"] = "bad"
    cases.append(bad_schema)
    bad_digest = copy.deepcopy(base)
    bad_digest[target_index]["proof_envelope"]["digest"] = "0" * 64
    cases.append(bad_digest)
    empty_refs = copy.deepcopy(base)
    empty_refs[target_index]["proof_envelope"]["refs"] = {}
    cases.append(empty_refs)
    fixture_only = copy.deepcopy(base)
    fixture_only[target_index]["proof_envelope"]["source"] = "fixture_only"
    cases.append(fixture_only)

    for results in cases:
        matrix = evaluate_release_matrix(results)
        assert matrix["ok"] is False
        assert matrix["proof_status"]["text_reply"]["missing"]


def test_release_matrix_rejects_corpus_proof_missing_required_ref():
    import copy
    import os
    from yinyo import build_proof_envelope, replay_scenarios
    from yinyo.release_matrix import evaluate_release_matrix

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    results = copy.deepcopy(replay_scenarios(os.path.join(repo, "examples", "feishu_scenarios.json")))
    target = next(item for item in results if item["name"] == "long_conversation")
    refs = dict(target["proof_envelope"]["refs"])
    refs.pop("retention_report")
    target["proof_envelope"] = build_proof_envelope(
        item=target,
        source=target["proof_envelope"]["source"],
        refs=refs,
    )

    matrix = evaluate_release_matrix(results)

    assert matrix["ok"] is False
    assert "proof_envelope.refs_required:retention_report" in matrix["proof_status"]["long_conversation"]["missing"]


def test_release_matrix_rejects_corpus_proof_contract_drift():
    import copy
    import os
    from yinyo import build_proof_envelope, replay_scenarios
    from yinyo.release_matrix import evaluate_release_matrix

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    base = replay_scenarios(os.path.join(repo, "examples", "feishu_scenarios.json"))
    expected = {
        "corpus_id": "proof_contract.corpus_id",
        "corpus_version": "proof_contract.corpus_version",
        "source": "proof_contract.source",
    }
    for field, blocker in expected.items():
        results = copy.deepcopy(base)
        target = next(item for item in results if item["name"] == "long_conversation")
        if field == "source":
            target["proof_envelope"] = build_proof_envelope(
                item=target,
                source="wrong_source",
                refs=target["proof_envelope"]["refs"],
            )
        else:
            target[field] = "wrong"
            target["proof_envelope"] = build_proof_envelope(
                item=target,
                source=target["proof_envelope"]["source"],
                refs=target["proof_envelope"]["refs"],
            )

        matrix = evaluate_release_matrix(results)

        assert matrix["ok"] is False
        assert blocker in matrix["proof_status"]["long_conversation"]["missing"]


def test_release_matrix_rejects_ack_boundary_semantic_drift():
    import copy
    import os
    from yinyo import build_proof_envelope, replay_scenarios
    from yinyo.release_matrix import evaluate_release_matrix

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    base = replay_scenarios(os.path.join(repo, "examples", "feishu_scenarios.json"))

    def set_latency(target, value):
        target["evidence"]["ack_latency_ms"] = value
        target["proof_envelope"]["refs"]["ack_latency_ms"] = value

    def set_deadline(target, value):
        target["evidence"]["ack_deadline_ms"] = value
        target["proof_envelope"]["refs"]["ack_deadline_ms"] = value

    cases = (
        ("refs_latency_drift", lambda target: target["proof_envelope"]["refs"].__setitem__("ack_latency_ms", target["evidence"]["ack_latency_ms"] + 1)),
        ("negative_latency", lambda target: set_latency(target, -1)),
        ("zero_deadline", lambda target: set_deadline(target, 0)),
        ("refs_job_drift", lambda target: target["proof_envelope"]["refs"].__setitem__("job_id", "wrong-job")),
    )
    for _name, mutate in cases:
        results = copy.deepcopy(base)
        target = next(item for item in results if item["name"] == "ack_boundary")
        mutate(target)
        target["proof_envelope"] = build_proof_envelope(
            item=target,
            source=target["proof_envelope"]["source"],
            refs=target["proof_envelope"]["refs"],
        )

        matrix = evaluate_release_matrix(results)

        assert matrix["ok"] is False
        assert "ack_boundary" in matrix["proof_status"]["ack_boundary"]["missing"]
        execution = next(row for row in matrix["harness_layers"]["rows"] if row["layer"] == "Execution")
        assert "ack_boundary" in execution["missing_proof"]


def test_release_matrix_rejects_state_handoff_resume_drift():
    import copy
    import os
    from yinyo import build_proof_envelope, replay_scenarios
    from yinyo.release_matrix import evaluate_release_matrix

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    base = replay_scenarios(os.path.join(repo, "examples", "feishu_scenarios.json"))
    for field in ("resume_artifacts_exist", "resume_budget_recoverable", "resume_trace_recoverable"):
        results = copy.deepcopy(base)
        target = next(item for item in results if item["name"] == "state_handoff")
        target["evidence"][field] = False
        target["proof_envelope"] = build_proof_envelope(
            item=target,
            source=target["proof_envelope"]["source"],
            refs=target["proof_envelope"]["refs"],
        )

        matrix = evaluate_release_matrix(results)

        assert matrix["ok"] is False
        assert "state_handoff" in matrix["proof_status"]["state_handoff"]["missing"]
        tooling = next(row for row in matrix["harness_layers"]["rows"] if row["layer"] == "Tooling")
        assert "state_handoff" in tooling["missing_proof"]


def test_release_matrix_rejects_tampered_result_after_digest():
    import copy
    import os
    from yinyo import replay_scenarios
    from yinyo.release_matrix import evaluate_release_matrix

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    results = copy.deepcopy(replay_scenarios(os.path.join(repo, "examples", "feishu_scenarios.json")))
    target = next(item for item in results if item["name"] == "text_reply")
    target["evidence"]["delivery"] = False

    matrix = evaluate_release_matrix(results)

    assert matrix["ok"] is False
    assert "proof_envelope.digest_mismatch" in matrix["proof_status"]["text_reply"]["missing"]


def test_cli_replay_scenarios_matrix_reports_3_6_evidence():
    import os
    import subprocess
    import sys

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [sys.executable, "scripts/replay_scenarios.py", "--matrix", "--corpus", "corpus/harness/scenarios.v1.json"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    data = json.loads(result.stdout)

    assert result.returncode == 0
    assert data["ok"] is True
    assert data["corpus"]["package_root_match"] is True
    assert len(data["corpus"]["sha256"]) == 64
    assert "image_understanding" in data["matrix"]["passed_scenarios"]
    assert data["matrix"]["scope"] == "local_harness_evidence"
    assert data["matrix"]["harness_layers"]["ok"] is True
    assert data["matrix"]["harness_layers"]["framework"] == "ETCLOVG"
    assert data["matrix"]["live_product_required_for_1_0"] is True
    assert any(item.get("corpus_id") == "release_gate" for item in data["scenarios"])
    assert data["matrix"]["proof_status"]["release_gate"]["proof"] == ["release_gate"]
    assert data["matrix"]["proof_status"]["ack_boundary"]["proof"] == ["ack_boundary"]
    assert data["matrix"]["proof_status"]["worker_saturation_backpressure"]["proof"] == ["worker_saturation"]
    assert data["matrix"]["proof_status"]["runtime_lock_single_writer"]["proof"] == ["runtime_lock"]
    assert data["matrix"]["proof_status"]["resource_quota"]["proof"] == ["resource_quota"]
    assert data["matrix"]["proof_status"]["adaptive_simplification"]["proof"] == ["adaptive_simplification"]
    assert any(row["id"] == "core.borrow_what_works" for row in data["matrix"]["rows"])
    fact_hygiene = next(row for row in data["matrix"]["rows"] if row["id"] == "trait.fact_hygiene")
    assert "fact_hygiene_policy" in fact_hygiene["required_scenarios"]
    assert "partial_failure" in fact_hygiene["live_product_required"]
    assert any(
        row["id"] == "trait.multidisciplinary"
        and "image_understanding" in row["required_scenarios"]
        and "long_conversation" in row["live_product_required"]
        for row in data["matrix"]["rows"]
    )


def test_cli_smoke_plan_lists_required_1_0_scenarios(tmp_path):
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "smoke",
            "plan",
            "--path",
            str(tmp_path / "smoke.jsonl"),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "YINYO 1.0 live smoke plan" in result.stdout
    assert "transport: ws" in result.stdout
    assert "url_verification" not in result.stdout
    assert "text_message_reply" in result.stdout
    assert "image_message_reply" in result.stdout
    assert "card_fallback" in result.stdout
    assert "duplicate_callback" in result.stdout
    assert "advanced live scenarios:" in result.stdout
    assert "image_understanding" in result.stdout
    assert "trace2skill_promotion" in result.stdout
    assert "yinyo smoke verify --transport ws --path" in result.stdout
    assert "--smoke-path is diagnostic only" in result.stdout
    assert "python scripts/verify_release.py --target 1.0.0 --config ./yinyo.env" in result.stdout
    assert "yinyo smoke bundle --config ./yinyo.env --output ./workspace/smoke-bundle --handoff-dir ./workspace/runs" in result.stdout
    assert "--live-attestation-id <attestation-id>" in result.stdout
    assert "--ws-sdk-session-id <ws-session-id>" not in result.stdout
    assert "python scripts/verify_release.py --target 1.0.0 --bundle ./workspace/smoke-bundle --candidate 1.0.0" in result.stdout
    assert "python scripts/verify_release.py --target 1.0.0 --smoke-path" not in result.stdout

    http_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "smoke",
            "plan",
            "--transport",
            "http",
            "--path",
            str(tmp_path / "smoke.jsonl"),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert http_result.returncode == 0
    assert "transport: http" in http_result.stdout
    assert "url_verification" in http_result.stdout


def test_live_smoke_runbook_covers_1_0_gate_and_3_6_evidence(tmp_path):
    from yinyo import RuntimeConfig, build_live_smoke_runbook, format_live_smoke_runbook

    cfg = RuntimeConfig.load(
        workspace=str(tmp_path),
        transport="ws",
        app_id="app",
        app_secret="super-secret",
        verify_token="verify-secret",
        deepseek_api_key="sk-secret",
        ws_sdk_session_id="session-live-runbook-001",
    )
    runbook = build_live_smoke_runbook(cfg, config_path="./yinyo.env")
    text = format_live_smoke_runbook(runbook)

    assert runbook["evidence_path"].endswith("smoke_evidence.jsonl")
    assert runbook["ws_sdk_session_id"] == "session-live-runbook-001"
    assert runbook["current_status"]["ok"] is False
    assert "smoke:text_message_reply" in runbook["current_status"]["missing"]
    assert "image_understanding" in runbook["current_status"]["advanced_missing"]
    assert any(item["scenario"] == "text_message_reply" for item in runbook["current_status"]["operator_plan"])
    assert runbook["current_status"]["handoff_summary"]["ready_to_handoff"] is True
    assert "current status:" in text
    assert "advanced_missing:" in text
    assert "frontier_readiness: yinyo.frontier_readiness.v1" in text
    assert "frontier_blockers:" in text
    assert "handoff_blocking_layers:" in text
    assert "url_verification" not in {item["scenario"] for item in runbook["live_scenarios"]}
    assert "text_message_reply" in text
    assert "image_message_reply" in text
    assert "card_fallback" in text
    assert "/yinyo-smoke card-fallback" in text
    assert "smoke_mode=true" in text
    assert "disable it and restart before collecting the remaining live scenarios" in text
    assert "The only smoke record allowed before the latest service_start is card_fallback" in text
    assert text.index("disable it and restart before collecting the remaining live scenarios") < text.index("yinyo smoke bundle --config ./yinyo.env")
    assert "duplicate_callback" in text
    assert "trace2skill_promotion" in text
    assert "partial_failure" in text
    assert "yinyo smoke record-advanced --config ./yinyo.env --scenario trace2skill_promotion" in text
    assert "yinyo smoke verify --transport ws" in text
    assert "yinyo smoke bundle --config ./yinyo.env" in text
    assert "--live-attestation-id <attestation-id>" in text
    assert "ws_sdk_session_id: session-live-runbook-001" in text
    assert "--ws-sdk-session-id session-live-runbook-001" in text
    assert "--ws-sdk-session-id <ws-session-id>" not in text
    assert "Set ws_sdk_session_id in yinyo.env before preflight" in text
    assert "smoke bundle inherits it from config" in text
    assert "service_start, ws_transport_start, and bundle live_provenance.ws_sdk_session_id" in text
    assert "python scripts/verify_secrets.py" in text
    assert "python scripts/verify_release.py --target 1.0.0 --bundle" in text
    assert "python scripts/replay_scenarios.py --matrix" in text
    assert "python scripts/verify_release.py --target 1.0.0" in text
    assert "super-secret" not in text
    assert "verify-secret" not in text
    assert "sk-secret" not in text


def test_cli_smoke_runbook_outputs_json_without_secret_echo(tmp_path):
    import subprocess
    import sys

    config_path = tmp_path / "runtime.env"
    config_path.write_text(
        "\n".join([
            f"workspace={tmp_path}",
            "transport=ws",
            "app_id=app",
            "app_secret=super-secret",
            "verify_token=verify-secret",
            "deepseek_api_key=sk-secret",
            "ws_sdk_session_id=session-live-runbook-json-001",
        ]),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "smoke",
            "runbook",
            "--config",
            str(config_path),
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    data = json.loads(result.stdout)

    assert result.returncode == 0
    assert data["title"] == "YINYO 1.0 live smoke runbook"
    assert data["transport"] == "ws"
    assert data["ws_sdk_session_id"] == "session-live-runbook-json-001"
    assert data["current_status"]["ok"] is False
    assert "smoke:text_message_reply" in data["current_status"]["missing"]
    assert "trace2skill_promotion" in data["current_status"]["advanced_missing"]
    assert data["current_status"]["operator_plan"]
    assert data["current_status"]["frontier_readiness"]["schema"] == "yinyo.frontier_readiness.v1"
    assert any(
        item["name"] == "State handoff transfer"
        for item in data["current_status"]["frontier_readiness"]["checks"]
    )
    assert data["current_status"]["handoff_summary"]["ready_to_handoff"] is True
    assert any("--ws-sdk-session-id session-live-runbook-json-001" in item for item in data["commands"])
    assert any(item["scenario"] == "duplicate_callback" for item in data["live_scenarios"])
    assert any(item["scenario"] == "memory_supersession" for item in data["local_3_6_evidence"])
    assert "super-secret" not in result.stdout
    assert "verify-secret" not in result.stdout
    assert "sk-secret" not in result.stdout


def test_cli_smoke_status_reports_missing_layers(tmp_path):
    import subprocess
    import sys

    config_path = tmp_path / "prod.env"
    config_path.write_text(f"workspace={tmp_path}\ntransport=http\n", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "smoke",
            "status",
            "--config",
            str(config_path),
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    data = json.loads(result.stdout)

    assert result.returncode == 1
    assert data["ok"] is False
    assert any(item["scenario"] == "text_message_reply" for item in data["scenarios"])
    assert any(item["scenario"] == "trace2skill_promotion" for item in data["advanced_scenarios"])
    assert any("smoke_record" in item["missing"] for item in data["scenarios"])
    assert any("smoke_record" in item["missing"] for item in data["advanced_scenarios"])
    assert data["next_actions"]
    assert data["snapshot"]["paths"]["smoke_evidence"].endswith("smoke_evidence.jsonl")
    assert data["snapshot"]["paths"]["runtime_lock"].endswith("yinyo_runtime.lock")
    assert data["snapshot"]["profile"] == "local"
    assert data["snapshot"]["transport"] == "http"
    assert data["snapshot"]["record_counts"]["smoke"] == 0
    assert data["operator_plan"]
    assert data["recovery_summary"]["service_last_status"] == "unknown"
    assert data["recovery_summary"]["runtime_lock_status"] == "available"
    assert data["recovery_summary"]["failed_jobs"] == 0
    assert data["handoff_summary"]["ready_to_handoff"] is True
    assert data["handoff_summary"]["release_ready"] is False
    assert data["frontier_readiness"]["schema"] == "yinyo.frontier_readiness.v1"
    assert data["frontier_readiness"]["local_matrix_ok"] is True
    assert data["frontier_readiness"]["harness_layers_ok"] is True
    assert data["frontier_readiness"]["live_chain_ok"] is False
    assert data["frontier_readiness"]["advanced_live_ok"] is False
    assert any(item["name"] == "TemporalTree state continuity" for item in data["frontier_readiness"]["checks"])
    assert any(item["name"] == "Trace-native failure diagnosis" for item in data["frontier_readiness"]["checks"])
    assert any(item["name"] == "Adaptive simplification guard" for item in data["frontier_readiness"]["checks"])
    assert "frontier_readiness_ok" in data["handoff_summary"]
    assert "basic" in data["handoff_summary"]["blocking_layers"]
    assert "advanced" in data["handoff_summary"]["blocking_layers"]
    assert "local_matrix" in data["handoff_summary"]["blocking_layers"]
    assert any(
        f"yinyo smoke record-advanced --config {config_path} --scenario trace2skill_promotion" in item
        for item in data["handoff_summary"]["next_operator_commands"]
    )
    assert any(item["layer"] == "basic" and item["scenario"] == "text_message_reply" for item in data["operator_plan"])
    basic_commands = {
        item["scenario"]: item["command"]
        for item in data["operator_plan"]
        if item["layer"] == "basic"
    }
    assert "yinyo serve is running" in basic_commands["text_message_reply"]
    assert "plain Feishu text message" in basic_commands["text_message_reply"]
    assert f"yinyo smoke status --config {config_path} --json" in basic_commands["text_message_reply"]
    assert "Feishu image message" in basic_commands["image_message_reply"]
    assert f"yinyo smoke status --config {config_path} --json" in basic_commands["image_message_reply"]
    assert "/yinyo-smoke card-fallback" in basic_commands["card_fallback"]
    assert "smoke_mode=false" in basic_commands["card_fallback"]
    assert f"yinyo smoke status --config {config_path} --json" in basic_commands["card_fallback"]
    assert "same Feishu event id" in basic_commands["duplicate_callback"]
    assert f"yinyo smoke status --config {config_path} --json" in basic_commands["duplicate_callback"]
    assert any(
        item["layer"] == "advanced"
        and item["scenario"] == "trace2skill_promotion"
        and f"yinyo smoke record-advanced --config {config_path} --scenario trace2skill_promotion" in item["command"]
        for item in data["operator_plan"]
    )
    assert not any("./yinyo.env" in item["command"] for item in data["operator_plan"])
    text_status = next(item for item in data["scenarios"] if item["scenario"] == "text_message_reply")
    assert "runtime_events_seen" in text_status
    assert "message_ids" in text_status
    trace2skill_status = next(item for item in data["advanced_scenarios"] if item["scenario"] == "trace2skill_promotion")
    assert trace2skill_status["required_fields"] == [
        "failure_trace_ref",
        "skill_ref",
        "validation_ref|regression_result_ref|regression_ref",
        "promotion_status",
        "post_promotion_run_ref",
    ]
    assert trace2skill_status["present_fields"] == []
    assert trace2skill_status["refs"] == {}


def test_cli_smoke_status_text_prints_operator_plan(tmp_path):
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "smoke",
            "status",
            "--workspace",
            str(tmp_path),
            "--transport",
            "ws",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "operator_plan:" in result.stdout
    assert "[basic] text_message_reply:" in result.stdout
    assert "[advanced] trace2skill_promotion:" in result.stdout
    assert "recovery_summary:" in result.stdout
    assert "handoff_blocking_layers:" in result.stdout


def test_cli_smoke_verify_text_reports_operator_summary(tmp_path):
    import subprocess
    import sys

    config_path = tmp_path / "runtime.env"
    config_path.write_text(f"workspace={tmp_path}\ntransport=ws\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "smoke",
            "verify",
            "--config",
            str(config_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "YINYO smoke evidence verify: INCOMPLETE" in result.stdout
    assert "basic_missing:" in result.stdout
    assert "advanced_missing:" in result.stdout
    assert "advanced_field_missing:" in result.stdout
    assert "advanced_ref_unresolved:" in result.stdout
    assert f"next: yinyo smoke status --config {config_path} --json" in result.stdout
    assert "{'ok':" not in result.stdout


def test_cli_smoke_verify_json_outputs_machine_readable_result(tmp_path):
    import json
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "smoke",
            "verify",
            "--workspace",
            str(tmp_path),
            "--transport",
            "ws",
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    data = json.loads(result.stdout)

    assert result.returncode == 1
    assert data["ok"] is False
    assert data["basic"]["missing"]
    assert data["advanced"]["missing"]
    assert data["path"].endswith("smoke_evidence.jsonl")


def test_smoke_preflight_passes_for_http_without_ws_sdk(tmp_path):
    from yinyo import RuntimeConfig, run_preflight

    cfg = RuntimeConfig.load(
        workspace=str(tmp_path),
        transport="http",
        app_id="app",
        app_secret="secret",
        verify_token="token",
        deepseek_api_key="sk-test",
    )
    result = run_preflight(cfg)
    checks = {item["name"]: item for item in result["checks"]}

    assert result["ok"] is True
    assert checks["runtime_config"]["ok"] is True
    assert checks["lark_oapi_sdk"]["ok"] is True
    assert "not required" in checks["lark_oapi_sdk"]["detail"]
    assert checks["smoke_evidence_path"]["ok"] is True
    assert checks["smoke_mode"]["ok"] is True
    assert "disabled" in checks["smoke_mode"]["detail"]


def test_smoke_preflight_validates_ws_session_provenance(tmp_path, monkeypatch):
    import types
    from yinyo import RuntimeConfig, run_preflight
    import yinyo.preflight as preflight

    class Builder:
        def register_p2_im_message_receive_v1(self, callback):
            return self

        def build(self):
            return "dispatcher"

    class EventDispatcherHandler:
        @staticmethod
        def builder(encrypt_key, verification_token):
            return Builder()

    class Client:
        pass

    monkeypatch.setattr(preflight.importlib.util, "find_spec", lambda name: object() if name == "lark_oapi" else None)
    monkeypatch.setattr(
        preflight.importlib,
        "import_module",
        lambda name: types.SimpleNamespace(
            EventDispatcherHandler=EventDispatcherHandler,
            ws=types.SimpleNamespace(Client=Client),
        ),
    )
    cfg = RuntimeConfig.load(
        workspace=str(tmp_path),
        transport="ws",
        app_id="app",
        app_secret="secret",
        deepseek_api_key="sk-test",
        ws_sdk_session_id="session-live-preflight-001",
    )
    result = run_preflight(cfg)
    checks = {item["name"]: item for item in result["checks"]}

    assert result["ok"] is True
    assert checks["ws_sdk_session_id"]["ok"] is True
    assert "service_start/ws_transport_start" in checks["ws_sdk_session_id"]["detail"]
    assert "inherited by smoke bundle" in checks["ws_sdk_session_id"]["detail"]
    assert "--ws-sdk-session-id must match if provided" in checks["ws_sdk_session_id"]["detail"]


def test_smoke_preflight_rejects_missing_or_placeholder_ws_session_provenance(tmp_path, monkeypatch):
    import types
    from yinyo import RuntimeConfig, run_preflight
    import yinyo.preflight as preflight

    class Builder:
        def register_p2_im_message_receive_v1(self, callback):
            return self

        def build(self):
            return "dispatcher"

    class EventDispatcherHandler:
        @staticmethod
        def builder(encrypt_key, verification_token):
            return Builder()

    class Client:
        pass

    monkeypatch.setattr(preflight.importlib.util, "find_spec", lambda name: object() if name == "lark_oapi" else None)
    monkeypatch.setattr(
        preflight.importlib,
        "import_module",
        lambda name: types.SimpleNamespace(
            EventDispatcherHandler=EventDispatcherHandler,
            ws=types.SimpleNamespace(Client=Client),
        ),
    )
    missing = RuntimeConfig.load(
        workspace=str(tmp_path / "missing"),
        transport="ws",
        app_id="app",
        app_secret="secret",
        deepseek_api_key="sk-test",
    )
    placeholder = RuntimeConfig.load(
        workspace=str(tmp_path / "placeholder"),
        transport="ws",
        app_id="app",
        app_secret="secret",
        deepseek_api_key="sk-test",
        ws_sdk_session_id="<ws-session-id>",
    )
    missing_result = run_preflight(missing)
    placeholder_result = run_preflight(placeholder)
    missing_check = {item["name"]: item for item in missing_result["checks"]}["ws_sdk_session_id"]
    placeholder_check = {item["name"]: item for item in placeholder_result["checks"]}["ws_sdk_session_id"]

    assert missing_result["ok"] is False
    assert missing_check["ok"] is False
    assert "preflight requires live provenance fields: ws_sdk_session_id" in missing_check["detail"]
    assert "Set ws_sdk_session_id in the same config" in missing_check["detail"]
    assert placeholder_result["ok"] is False
    assert placeholder_check["ok"] is False
    assert "preflight rejects placeholder live provenance fields: ws_sdk_session_id" in placeholder_check["detail"]


def test_smoke_preflight_validates_lark_oapi_contract():
    import types
    import pytest
    from yinyo.preflight import _validate_lark_oapi_contract

    class Builder:
        def register_p2_im_message_receive_v1(self, callback):
            return self

        def build(self):
            return "dispatcher"

    class EventDispatcherHandler:
        @staticmethod
        def builder(encrypt_key, verification_token):
            return Builder()

    class Client:
        pass

    good = types.SimpleNamespace(
        EventDispatcherHandler=EventDispatcherHandler,
        ws=types.SimpleNamespace(Client=Client),
    )
    _validate_lark_oapi_contract(good)

    class BadBuilder:
        def build(self):
            return "dispatcher"

    class BadEventDispatcherHandler:
        @staticmethod
        def builder(encrypt_key, verification_token):
            return BadBuilder()

    bad = types.SimpleNamespace(
        EventDispatcherHandler=BadEventDispatcherHandler,
        ws=types.SimpleNamespace(Client=Client),
    )
    with pytest.raises(RuntimeError, match="register_p2_im_message_receive_v1"):
        _validate_lark_oapi_contract(bad)


def test_smoke_preflight_reports_invalid_lark_oapi_contract(tmp_path, monkeypatch):
    import types
    from yinyo import RuntimeConfig, run_preflight
    import yinyo.preflight as preflight

    class Spec:
        pass

    monkeypatch.setattr(preflight.importlib.util, "find_spec", lambda name: Spec() if name == "lark_oapi" else None)
    monkeypatch.setattr(
        preflight.importlib,
        "import_module",
        lambda name: types.SimpleNamespace(EventDispatcherHandler=types.SimpleNamespace(), ws=types.SimpleNamespace()),
    )
    cfg = RuntimeConfig.load(
        workspace=str(tmp_path),
        transport="ws",
        app_id="app",
        app_secret="secret",
        deepseek_api_key="sk-test",
    )
    result = run_preflight(cfg)
    check = next(item for item in result["checks"] if item["name"] == "lark_oapi_sdk")

    assert result["ok"] is False
    assert check["ok"] is False
    assert "SDK contract invalid" in check["detail"]
    assert "EventDispatcherHandler.builder" in check["detail"]


def test_smoke_preflight_reports_enabled_smoke_mode(tmp_path):
    from yinyo import RuntimeConfig, format_preflight, run_preflight

    cfg = RuntimeConfig.load(
        workspace=str(tmp_path),
        transport="http",
        app_id="app",
        app_secret="secret",
        verify_token="token",
        deepseek_api_key="sk-test",
        smoke_mode=True,
    )
    result = run_preflight(cfg)
    checks = {item["name"]: item for item in result["checks"]}
    text = format_preflight(result)

    assert result["ok"] is True
    assert checks["smoke_mode"]["ok"] is True
    assert "enabled" in checks["smoke_mode"]["detail"]
    assert "/yinyo-smoke card-fallback" in text


def test_smoke_preflight_rejects_existing_evidence_before_fresh_live_run(tmp_path):
    from yinyo import RuntimeConfig, reset_smoke_evidence_files, run_preflight

    cfg = RuntimeConfig.load(
        workspace=str(tmp_path),
        transport="http",
        app_id="app",
        app_secret="secret",
        verify_token="token",
        deepseek_api_key="sk-test",
    )
    cfg.apply_defaults()
    for path in (cfg.smoke_evidence_path, cfg.log_path, cfg.job_store_path, cfg.event_store_path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write('{"stale": true}\n')

    result = run_preflight(cfg)
    checks = {item["name"]: item for item in result["checks"]}
    allowed = run_preflight(cfg, allow_existing_evidence=True)
    reset_smoke_evidence_files(
        smoke_path=cfg.smoke_evidence_path,
        log_path=cfg.log_path,
        job_store_path=cfg.job_store_path,
        event_store_path=cfg.event_store_path,
        confirm=True,
    )
    after_reset = run_preflight(cfg)

    assert result["ok"] is False
    assert checks["fresh_evidence_files"]["ok"] is False
    assert "existing evidence records found" in checks["fresh_evidence_files"]["detail"]
    assert "yinyo smoke reset --config <config> --confirm-reset" in checks["fresh_evidence_files"]["detail"]
    assert allowed["ok"] is True
    assert after_reset["ok"] is True


def test_cli_smoke_preflight_allows_existing_evidence_only_with_explicit_flag(tmp_path):
    import subprocess
    import sys

    config_path = tmp_path / "runtime.env"
    config_path.write_text(
        "\n".join([
            f"workspace={tmp_path}",
            "transport=http",
            "app_id=app",
            "app_secret=secret",
            "verify_token=token",
            "deepseek_api_key=sk-test",
        ]),
        encoding="utf-8",
    )
    stale = tmp_path / "smoke_evidence.jsonl"
    stale.write_text('{"stale": true}\n', encoding="utf-8")

    base = [
        sys.executable,
        "-m",
        "yinyo.cli",
        "smoke",
        "preflight",
        "--config",
        str(config_path),
    ]
    rejected = subprocess.run(base + ["--json"], text=True, capture_output=True, check=False)
    allowed = subprocess.run(base + ["--allow-existing-evidence", "--json"], text=True, capture_output=True, check=False)

    assert rejected.returncode == 1
    assert "fresh_evidence_files" in rejected.stdout
    assert "existing evidence records found" in rejected.stdout
    assert allowed.returncode == 0
    assert '"allow_existing_evidence": true' in allowed.stdout


def test_cli_smoke_preflight_reports_missing_ws_session_id(tmp_path):
    import subprocess
    import sys

    config_path = tmp_path / "runtime.env"
    config_path.write_text(
        "\n".join([
            f"workspace={tmp_path}",
            "transport=ws",
            "app_id=app",
            "app_secret=secret",
            "deepseek_api_key=sk-test",
        ]),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "smoke",
            "preflight",
            "--config",
            str(config_path),
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    data = json.loads(result.stdout)
    checks = {item["name"]: item for item in data["checks"]}

    assert result.returncode == 1
    assert data["ok"] is False
    assert checks["ws_sdk_session_id"]["ok"] is False
    assert "ws_sdk_session_id" in checks["ws_sdk_session_id"]["detail"]
    assert "same config used by smoke bundle" in checks["ws_sdk_session_id"]["detail"]
    assert "--ws-sdk-session-id is provided, it must match" in checks["ws_sdk_session_id"]["detail"]
    assert "secret" not in result.stdout
    assert "sk-test" not in result.stdout


def test_cli_smoke_preflight_reports_missing_config_without_secret_echo(tmp_path):
    import subprocess
    import sys

    config_path = tmp_path / "runtime.env"
    config_path.write_text(
        "\n".join([
            f"workspace={tmp_path}",
            "transport=http",
            "app_secret=super-secret",
        ]),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "smoke",
            "preflight",
            "--config",
            str(config_path),
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    data = json.loads(result.stdout)

    assert result.returncode == 1
    assert data["ok"] is False
    assert "super-secret" not in result.stdout
    runtime_config = next(item for item in data["checks"] if item["name"] == "runtime_config")
    assert runtime_config["ok"] is False
    assert "do not paste raw secrets into chat" in runtime_config["detail"]
    assert "Rotate any credential" in runtime_config["detail"]


def test_smoke_evidence_requires_all_live_1_0_scenarios(tmp_path):
    from yinyo import SmokeEvidenceRecorder, verify_smoke_evidence

    path = tmp_path / "smoke.jsonl"
    recorder = SmokeEvidenceRecorder(str(path))
    recorder.record("url_verification", "passed", live=True)
    recorder.record("text_message_reply", "passed", live=True)
    recorder.record("image_message_reply", "passed", live=False)

    result = verify_smoke_evidence(str(path))

    assert result["ok"] is False
    assert "image_message_reply" in result["missing"]
    assert "card_fallback" in result["missing"]
    assert "duplicate_callback" in result["missing"]


def test_smoke_evidence_accepts_complete_live_set(tmp_path):
    from yinyo import SmokeEvidenceRecorder, verify_smoke_evidence
    from yinyo.smoke import REQUIRED_1_0_SCENARIOS

    path = tmp_path / "smoke.jsonl"
    recorder = SmokeEvidenceRecorder(str(path))
    for scenario in REQUIRED_1_0_SCENARIOS:
        recorder.record(scenario, "passed", live=True, token="verify_token=secret-token")

    text = path.read_text(encoding="utf-8")
    result = verify_smoke_evidence(str(path))

    assert result["ok"] is True
    assert result["missing"] == []
    assert "secret-token" not in text


def test_cli_smoke_verify_requires_advanced_live_evidence(tmp_path):
    import subprocess
    import sys
    from yinyo import SmokeEvidenceRecorder
    from yinyo.smoke import REQUIRED_1_0_SCENARIOS

    path = tmp_path / "smoke.jsonl"
    recorder = SmokeEvidenceRecorder(str(path))
    for scenario in REQUIRED_1_0_SCENARIOS:
        recorder.record(scenario, "passed", live=True)

    missing_advanced = subprocess.run(
        [sys.executable, "-m", "yinyo.cli", "smoke", "verify", "--path", str(path)],
        text=True,
        capture_output=True,
        check=False,
    )
    _record_advanced_live_evidence(recorder)
    complete = subprocess.run(
        [sys.executable, "-m", "yinyo.cli", "smoke", "verify", "--path", str(path)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert missing_advanced.returncode == 1
    assert "YINYO smoke evidence verify: INCOMPLETE" in missing_advanced.stdout
    assert "advanced_missing:" in missing_advanced.stdout
    assert "image_understanding" in missing_advanced.stdout
    assert complete.returncode == 0
    assert "YINYO smoke evidence verify: OK" in complete.stdout
    assert "advanced_missing: []" in complete.stdout


def test_cli_smoke_verify_uses_transport_scoped_basic_scenarios(tmp_path):
    import subprocess
    import sys
    from yinyo import SmokeEvidenceRecorder
    from yinyo.smoke import REQUIRED_1_0_WS_SCENARIOS

    path = tmp_path / "smoke.jsonl"
    recorder = SmokeEvidenceRecorder(str(path))
    for scenario in REQUIRED_1_0_WS_SCENARIOS:
        recorder.record(scenario, "passed", live=True)
    _record_advanced_live_evidence(recorder)

    result = subprocess.run(
        [sys.executable, "-m", "yinyo.cli", "smoke", "verify", "--transport", "ws", "--path", str(path)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "YINYO smoke evidence verify: OK" in result.stdout
    assert "basic_missing: []" in result.stdout
    assert "url_verification" not in result.stdout


def test_gateway_records_live_url_verification_smoke_evidence(tmp_path):
    from yinyo import FeishuRuntimeGateway, RuntimeLogger, SmokeEvidenceRecorder

    class Adapter:
        pass

    smoke_path = tmp_path / "smoke.jsonl"
    gateway = FeishuRuntimeGateway(
        adapter=Adapter(),
        verify_token="good-token",
        logger=RuntimeLogger(str(tmp_path / "runtime.jsonl")),
        smoke_recorder=SmokeEvidenceRecorder(str(smoke_path)),
    )

    result = gateway.handle_event({
        "type": "url_verification",
        "token": "good-token",
        "challenge": "challenge-token",
    }, async_dispatch=False)
    record = json.loads(smoke_path.read_text(encoding="utf-8").splitlines()[0])

    assert result.body == {"challenge": "challenge-token"}
    assert record["scenario"] == "url_verification"
    assert record["status"] == "passed"
    assert record["live"] is True
    log = json.loads((tmp_path / "runtime.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert log["event"] == "webhook_url_verification"


def test_gateway_records_image_and_card_fallback_live_smoke_evidence(tmp_path, monkeypatch):
    from yinyo import FeishuRuntimeGateway, SmokeEvidenceRecorder

    class Session:
        def is_duplicate(self, text, user_id):
            return False

    class Agent:
        session_manager = Session()

        def handle_message(self, user_id, chat_id, text, already_deduped=False, correlation_id=""):
            return {"text": "ok", "files": [{"path": "report.md"}], "run_id": "run-1"}

    class Adapter:
        agent = Agent()

        def add_reaction(self, message_id):
            return True

        def remove_reaction(self, message_id):
            return True

        def send_message(self, *args, **kwargs):
            return {"success": True, "message_ids": ["om_reply"], "fallback": True}

        def _download_image(self, image_key):
            return image_key

    class VisionAdapter:
        def describe(self, image_path, prompt):
            return {"description": "image description"}

    import yinyo.vision_adapter

    monkeypatch.setattr(yinyo.vision_adapter, "get_vision_adapter", lambda: VisionAdapter())
    smoke_path = tmp_path / "smoke.jsonl"
    gateway = FeishuRuntimeGateway(
        adapter=Adapter(),
        agent=Adapter.agent,
        verify_token="good-token",
        smoke_recorder=SmokeEvidenceRecorder(str(smoke_path)),
    )

    result = gateway.handle_event({
        "type": "event_callback",
        "uuid": "evt_image_1",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "image",
                "content": json.dumps({"image_key": "img_1"}),
                "chat_id": "oc_1",
                "message_id": "om_1",
            },
        },
    }, async_dispatch=False)
    records = [json.loads(line) for line in smoke_path.read_text(encoding="utf-8").splitlines()]

    assert gateway.get_job(result.job_id).result["fallback"] is True
    assert [record["scenario"] for record in records] == ["image_message_reply", "card_fallback"]
    assert all(record["live"] is True for record in records)
    assert all(record["status"] == "passed" for record in records)


def test_gateway_records_duplicate_callback_live_smoke_evidence(tmp_path):
    from yinyo import FeishuRuntimeGateway, JsonlEventStore, SmokeEvidenceRecorder

    class Session:
        def is_duplicate(self, text, user_id):
            return False

    class Agent:
        session_manager = Session()

        def handle_message(self, user_id, chat_id, text, already_deduped=False, correlation_id=""):
            return {"text": "ok", "files": []}

    class Adapter:
        agent = Agent()

        def add_reaction(self, message_id):
            return True

        def remove_reaction(self, message_id):
            return True

        def send_message(self, *args, **kwargs):
            return {"success": True, "message_ids": ["om_reply"], "fallback": False}

        def _download_image(self, image_key):
            return image_key

    event = {
        "type": "event_callback",
        "uuid": "evt_duplicate_1",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": "hello"}),
                "chat_id": "oc_1",
                "message_id": "om_1",
            },
        },
    }
    smoke_path = tmp_path / "smoke.jsonl"
    store_path = tmp_path / "events.jsonl"
    first = FeishuRuntimeGateway(
        adapter=Adapter(),
        agent=Adapter.agent,
        verify_token="good-token",
        event_store=JsonlEventStore(str(store_path)),
        smoke_recorder=SmokeEvidenceRecorder(str(smoke_path)),
    )
    first.handle_event(event, async_dispatch=False)
    second = FeishuRuntimeGateway(
        adapter=Adapter(),
        agent=Adapter.agent,
        verify_token="good-token",
        event_store=JsonlEventStore(str(store_path)),
        smoke_recorder=SmokeEvidenceRecorder(str(smoke_path)),
    )
    duplicate = second.handle_event(event, async_dispatch=False)
    records = [json.loads(line) for line in smoke_path.read_text(encoding="utf-8").splitlines()]

    assert duplicate.duplicate is True
    assert records[-1]["scenario"] == "duplicate_callback"
    assert records[-1]["status"] == "passed"
    assert records[-1]["live"] is True


def test_gateway_generated_live_smoke_set_can_pass_1_0_verifier(tmp_path, monkeypatch):
    from yinyo import FeishuRuntimeGateway, JsonlEventStore, SmokeEvidenceRecorder, verify_smoke_evidence

    class Session:
        def is_duplicate(self, text, user_id):
            return False

    class Agent:
        session_manager = Session()

        def handle_message(self, user_id, chat_id, text, already_deduped=False, correlation_id=""):
            return {"text": "ok", "files": [{"path": "report.md"}], "run_id": f"run-{correlation_id}"}

    class Adapter:
        agent = Agent()

        def add_reaction(self, message_id):
            return True

        def remove_reaction(self, message_id):
            return True

        def send_message(self, *args, **kwargs):
            return {"success": True, "message_ids": ["om_reply"], "fallback": bool(kwargs.get("files"))}

        def _download_image(self, image_key):
            return image_key

    class VisionAdapter:
        def describe(self, image_path, prompt):
            return {"description": "image description"}

    import yinyo.vision_adapter

    monkeypatch.setattr(yinyo.vision_adapter, "get_vision_adapter", lambda: VisionAdapter())
    smoke_path = tmp_path / "smoke.jsonl"
    store_path = tmp_path / "events.jsonl"
    gateway = FeishuRuntimeGateway(
        adapter=Adapter(),
        agent=Adapter.agent,
        verify_token="good-token",
        event_store=JsonlEventStore(str(store_path)),
        smoke_recorder=SmokeEvidenceRecorder(str(smoke_path)),
    )

    gateway.handle_event({"type": "url_verification", "token": "good-token", "challenge": "challenge"}, async_dispatch=False)
    text_event = {
        "type": "event_callback",
        "uuid": "evt_text_1",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": "hello"}),
                "chat_id": "oc_1",
                "message_id": "om_text_1",
            },
        },
    }
    image_event = {
        "type": "event_callback",
        "uuid": "evt_image_1",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "image",
                "content": json.dumps({"image_key": "img_1"}),
                "chat_id": "oc_1",
                "message_id": "om_image_1",
            },
        },
    }
    gateway.handle_event(text_event, async_dispatch=False)
    gateway.handle_event(image_event, async_dispatch=False)
    gateway.handle_event(text_event, async_dispatch=False)

    result = verify_smoke_evidence(str(smoke_path))

    assert result["ok"] is True
    assert result["missing"] == []


def test_cli_smoke_verify_fails_without_complete_live_evidence(tmp_path):
    import os
    import subprocess
    import sys

    path = tmp_path / "smoke.jsonl"
    path.write_text('{"scenario":"url_verification","status":"passed","live":true}\n', encoding="utf-8")
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ)
    env["PYTHONPATH"] = repo + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [sys.executable, "-m", "yinyo.cli", "smoke", "verify", "--path", str(path)],
        cwd=str(tmp_path),
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )

    assert result.returncode == 1
    assert "duplicate_callback" in result.stdout


def test_cli_smoke_record_advanced_writes_valid_redacted_evidence(tmp_path):
    import os
    import subprocess
    import sys

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ)
    env["PYTHONPATH"] = repo + os.pathsep + env.get("PYTHONPATH", "")
    commands = [
        ["--scenario", "image_understanding", "--image-ref", "image api_key=abcd1234abcd1234"],
        ["--scenario", "long_conversation", "--transcript-ref", "transcript api_key=abcd1234abcd1234"],
        ["--scenario", "memory_supersession", "--memory-ref", "memory-secret-1"],
        [
            "--scenario",
            "trace2skill_promotion",
            "--failure-trace-ref",
            "trace-secret-1",
            "--skill-ref",
            "skill-secret-1",
            "--regression-result-ref",
            "regression-secret-1",
            "--promotion-status",
            "proven",
            "--post-promotion-run-ref",
            "run-secret-1",
        ],
        ["--scenario", "deepseek_usage", "--model-usage", '{"prompt_tokens":10,"completion_tokens":3,"total_tokens":13}'],
        ["--scenario", "partial_failure", "--failure-ref", "failure-secret-1"],
    ]
    last = None
    for extra in commands:
        last = subprocess.run(
            [
                sys.executable,
                "-m",
                "yinyo.cli",
                "smoke",
                "record-advanced",
                "--workspace",
                str(tmp_path),
                "--transport",
                "http",
                "--json",
                *extra,
            ],
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )
        assert last.returncode == 0, last.stderr

    data = json.loads(last.stdout)
    smoke_text = (tmp_path / "smoke_evidence.jsonl").read_text(encoding="utf-8")

    assert data["advanced"]["ok"] is True
    assert data["advanced"]["missing"] == []
    assert data["advanced"]["field_missing"] == []
    assert data["advanced"]["source_missing"] == []
    assert data["advanced"]["proof_missing"] == []
    assert data["advanced"]["proof_mismatch"] == []
    assert data["record"]["advanced_proof"]["schema"] == "yinyo.advanced_live_proof.v1"
    assert len(data["record"]["advanced_proof"]["digest"]) == 64
    assert "abcd1234abcd1234" not in smoke_text
    assert "[REDACTED]" in smoke_text


def test_record_advanced_live_evidence_adds_verifiable_proof(tmp_path):
    from yinyo import record_advanced_live_evidence, verify_advanced_live_evidence

    smoke_path = str(tmp_path / "smoke.jsonl")
    result = record_advanced_live_evidence(
        smoke_path,
        "deepseek_usage",
        model_usage={"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
    )

    proof = result["record"]["advanced_proof"]
    verified = verify_advanced_live_evidence(smoke_path, required={"deepseek_usage"})

    assert proof["schema"] == "yinyo.advanced_live_proof.v1"
    assert proof["scenario"] == "deepseek_usage"
    assert proof["refs"] == ["model_usage"]
    assert len(proof["digest"]) == 64
    assert verified["ok"] is True
    assert verified["proof_missing"] == []
    assert verified["proof_mismatch"] == []
    assert verified["ref_unresolved"] == []
    assert verified["ref_status"]["deepseek_usage"]["ok"] is True


def test_trace2skill_advanced_live_evidence_resolves_validation_ref(tmp_path):
    from yinyo import record_advanced_live_evidence, verify_advanced_live_evidence

    validation_dir = tmp_path / "skills" / "retry-file-write" / "validation"
    validation_dir.mkdir(parents=True)
    validation_path = validation_dir / "validation.json"
    validation_path.write_text(
        json.dumps({
            "schema": "yinyo.trace2skill_validation.v1",
            "skill_name": "retry-file-write",
            "failure_trace_ref": "trace2skill:abc",
            "passed": True,
            "checks": {
                "pre_skill_failure_reproduced": True,
                "post_skill_guardrail_applied": True,
                "pre_skill_command_failed_as_expected": True,
                "post_skill_command_passed": True,
            },
            "pre_skill_result": {"path": str(validation_dir / "pre-skill-regression.json"), "exit_code": 1},
            "post_skill_result": {"path": str(validation_dir / "post-skill-regression.json"), "exit_code": 0, "passed": True},
            "replay_result": {"passed": True, "exit_code": 0},
        }),
        encoding="utf-8",
    )
    skill_path = tmp_path / "skills" / "retry-file-write" / "meta.json"
    skill_path.write_text(json.dumps({"name": "retry-file-write", "status": "proven"}), encoding="utf-8")
    smoke_path = str(tmp_path / "smoke.jsonl")

    record_advanced_live_evidence(
        smoke_path,
        "trace2skill_promotion",
        failure_trace_ref="trace2skill:abc",
        skill_ref=str(skill_path),
        validation_ref=str(validation_path),
        promotion_status="proven",
        post_promotion_run_ref=str(validation_path),
    )
    verified = verify_advanced_live_evidence(smoke_path, required={"trace2skill_promotion"})

    assert verified["ok"] is True
    assert verified["ref_unresolved"] == []
    status = verified["ref_status"]["trace2skill_promotion"]
    assert status["resolved"]["validation_ref"]["kind"] == "trace2skill_validation"
    assert status["resolved"]["validation_ref"]["pre_skill_failed"] is True
    assert status["resolved"]["validation_ref"]["post_skill_passed"] is True
    assert status["resolved"]["trace2skill_validation"]["status"] == "resolved"


def test_trace2skill_advanced_live_evidence_rejects_weak_validation_ref_before_write(tmp_path):
    from yinyo import record_advanced_live_evidence

    validation_path = tmp_path / "validation.json"
    validation_path.write_text(
        json.dumps({
            "schema": "yinyo.trace2skill_validation.v1",
            "skill_name": "retry-file-write",
            "failure_trace_ref": "trace2skill:abc",
            "passed": True,
            "replay_result": {"passed": True, "exit_code": 0},
        }),
        encoding="utf-8",
    )
    skill_path = tmp_path / "meta.json"
    skill_path.write_text(json.dumps({"name": "retry-file-write", "status": "proven"}), encoding="utf-8")
    smoke_path = str(tmp_path / "smoke.jsonl")

    try:
        record_advanced_live_evidence(
            smoke_path,
            "trace2skill_promotion",
            failure_trace_ref="trace2skill:abc",
            skill_ref=str(skill_path),
            validation_ref=str(validation_path),
            promotion_status="proven",
            post_promotion_run_ref=str(validation_path),
        )
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("weak Trace2Skill validation ref should be refused before write")

    assert "validation_incomplete" in message
    assert not (tmp_path / "smoke.jsonl").exists()


def test_advanced_live_evidence_rejects_missing_local_ref_path(tmp_path):
    from yinyo import record_advanced_live_evidence

    smoke_path = str(tmp_path / "smoke.jsonl")
    missing_path = tmp_path / "missing-validation.json"
    try:
        record_advanced_live_evidence(
            smoke_path,
            "trace2skill_promotion",
            failure_trace_ref="trace2skill:abc",
            skill_ref="skill-redacted-1",
            validation_ref=str(missing_path),
            promotion_status="proven",
            post_promotion_run_ref="run-redacted-1",
        )
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("missing local validation ref should be refused before write")

    assert "validation_ref:file_missing" in message
    assert not (tmp_path / "smoke.jsonl").exists()


def test_advanced_live_evidence_rejects_missing_or_tampered_proof(tmp_path):
    from yinyo import record_advanced_live_evidence, verify_advanced_live_evidence

    smoke_path = tmp_path / "smoke.jsonl"
    record_advanced_live_evidence(str(smoke_path), "image_understanding", image_ref="image-redacted-1")

    record = json.loads(smoke_path.read_text(encoding="utf-8").splitlines()[0])
    record.pop("advanced_proof")
    smoke_path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    missing = verify_advanced_live_evidence(str(smoke_path), required={"image_understanding"})

    record["advanced_proof"] = {
        "schema": "yinyo.advanced_live_proof.v1",
        "scenario": "image_understanding",
        "refs": ["image_ref"],
        "digest": "0" * 64,
    }
    smoke_path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    tampered = verify_advanced_live_evidence(str(smoke_path), required={"image_understanding"})

    assert missing["ok"] is False
    assert missing["proof_missing"] == ["image_understanding"]
    assert tampered["ok"] is False
    assert tampered["proof_mismatch"] == ["image_understanding"]


def test_full_smoke_status_reports_advanced_proof_failures(tmp_path):
    from yinyo import build_smoke_evidence_status, record_advanced_live_evidence

    smoke_path = tmp_path / "smoke.jsonl"
    log_path = tmp_path / "runtime.jsonl"
    job_path = tmp_path / "runtime_jobs.jsonl"
    event_path = tmp_path / "gateway_events.jsonl"
    record_advanced_live_evidence(str(smoke_path), "image_understanding", image_ref="image-redacted-1")
    record = json.loads(smoke_path.read_text(encoding="utf-8").splitlines()[0])
    record["advanced_proof"]["digest"] = "0" * 64
    smoke_path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")

    status = build_smoke_evidence_status(
        smoke_path=str(smoke_path),
        log_path=str(log_path),
        job_store_path=str(job_path),
        event_store_path=str(event_path),
    )
    image_status = next(item for item in status["advanced_scenarios"] if item["scenario"] == "image_understanding")

    assert status["ok"] is False
    assert "advanced_proof_mismatch:image_understanding" in status["chain"]["missing"]
    assert image_status["ok"] is False
    assert "proof_digest" in image_status["missing"]
    assert image_status["proof_schema"] == "yinyo.advanced_live_proof.v1"
    assert image_status["proof_digest"] == "0" * 64
    assert any(
        item["layer"] == "advanced"
        and item["scenario"] == "image_understanding"
        and "proof_digest" in item["missing"]
        for item in status["operator_plan"]
    )


def test_full_smoke_evidence_reports_unresolved_advanced_refs(tmp_path):
    from yinyo import SmokeEvidenceRecorder, verify_full_smoke_evidence

    smoke_path = tmp_path / "smoke.jsonl"
    log_path = tmp_path / "runtime.jsonl"
    job_path = tmp_path / "runtime_jobs.jsonl"
    event_path = tmp_path / "gateway_events.jsonl"
    recorder = SmokeEvidenceRecorder(str(smoke_path))
    missing_validation = tmp_path / "missing-validation.json"
    recorder.record(
        "trace2skill_promotion",
        "passed",
        live=True,
        evidence_source="yinyo smoke record-advanced",
        failure_trace_ref="trace2skill:abc",
        skill_ref="skill-redacted-1",
        validation_ref=str(missing_validation),
        promotion_status="proven",
        post_promotion_run_ref="run-redacted-1",
        advanced_proof={
            "schema": "yinyo.advanced_live_proof.v1",
            "scenario": "trace2skill_promotion",
            "refs": [
                "failure_trace_ref",
                "post_promotion_run_ref",
                "promotion_status",
                "skill_ref",
                "validation_ref",
            ],
            "digest": "0" * 64,
        },
    )

    result = verify_full_smoke_evidence(
        smoke_path=str(smoke_path),
        log_path=str(log_path),
        job_store_path=str(job_path),
        event_store_path=str(event_path),
    )

    assert result["ok"] is False
    assert any(
        item.startswith("advanced_ref_unresolved:trace2skill_promotion:validation_ref:file_missing")
        for item in result["missing"]
    )


def test_advanced_live_evidence_rejects_handwritten_records(tmp_path):
    from yinyo import SmokeEvidenceRecorder, verify_advanced_live_evidence

    recorder = SmokeEvidenceRecorder(str(tmp_path / "smoke.jsonl"))
    recorder.record("image_understanding", "passed", live=True, image_ref="image-redacted-1")
    recorder.record("long_conversation", "passed", live=True, transcript_ref="redacted-transcript-1")
    recorder.record("memory_supersession", "passed", live=True, memory_ref="mem-redacted-1")
    recorder.record(
        "trace2skill_promotion",
        "passed",
        live=True,
        failure_trace_ref="trace-redacted-1",
        skill_ref="skill-retry-file-write",
        regression_result_ref="regression-redacted-1",
        promotion_status="proven",
        post_promotion_run_ref="post-promotion-run-redacted-1",
    )
    recorder.record(
        "deepseek_usage",
        "passed",
        live=True,
        model_usage={"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
    )
    recorder.record("partial_failure", "passed", live=True, failure_ref="failure-redacted-1")

    result = verify_advanced_live_evidence(recorder.path)

    assert result["ok"] is False
    assert result["missing"] == []
    assert result["field_missing"] == []
    assert result["source_missing"] == [
        "deepseek_usage",
        "image_understanding",
        "long_conversation",
        "memory_supersession",
        "partial_failure",
        "trace2skill_promotion",
    ]
    assert result["proof_missing"] == [
        "deepseek_usage",
        "image_understanding",
        "long_conversation",
        "memory_supersession",
        "partial_failure",
        "trace2skill_promotion",
    ]


def test_cli_smoke_record_advanced_rejects_missing_required_fields(tmp_path):
    import os
    import subprocess
    import sys

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ)
    env["PYTHONPATH"] = repo + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "smoke",
            "record-advanced",
            "--workspace",
            str(tmp_path),
            "--transport",
            "http",
            "--scenario",
            "trace2skill_promotion",
            "--skill-ref",
            "skill-only",
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )

    assert result.returncode == 2
    assert "failure_trace_ref" in result.stderr
    assert not (tmp_path / "smoke_evidence.jsonl").exists()


def test_cli_smoke_record_advanced_rejects_missing_local_ref_before_write(tmp_path):
    import os
    import subprocess
    import sys

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ)
    env["PYTHONPATH"] = repo + os.pathsep + env.get("PYTHONPATH", "")
    missing_path = tmp_path / "missing-validation.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "yinyo.cli",
            "smoke",
            "record-advanced",
            "--workspace",
            str(tmp_path),
            "--transport",
            "http",
            "--scenario",
            "trace2skill_promotion",
            "--failure-trace-ref",
            "trace2skill:abc",
            "--skill-ref",
            "skill-redacted-1",
            "--validation-ref",
            str(missing_path),
            "--promotion-status",
            "proven",
            "--post-promotion-run-ref",
            "run-redacted-1",
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )

    assert result.returncode == 2
    assert "validation_ref:file_missing" in result.stderr
    assert not (tmp_path / "smoke_evidence.jsonl").exists()


def test_trace2skill_advanced_live_evidence_requires_proven_promotion_status(tmp_path):
    from yinyo import record_advanced_live_evidence, verify_advanced_live_evidence

    smoke_path = str(tmp_path / "smoke.jsonl")
    try:
        record_advanced_live_evidence(
            smoke_path,
            "trace2skill_promotion",
            failure_trace_ref="trace-redacted-1",
            skill_ref="skill-redacted-1",
            regression_result_ref="regression-redacted-1",
            promotion_status="draft",
            post_promotion_run_ref="run-redacted-1",
        )
    except ValueError as exc:
        assert "promotion_status" in str(exc)
    else:
        raise AssertionError("draft Trace2Skill promotion status should be rejected")

    record_advanced_live_evidence(
        smoke_path,
        "trace2skill_promotion",
        failure_trace_ref="trace-redacted-1",
        skill_ref="skill-redacted-1",
        regression_result_ref="regression-redacted-1",
        promotion_status="stable",
        post_promotion_run_ref="run-redacted-1",
    )

    result = verify_advanced_live_evidence(smoke_path, required={"trace2skill_promotion"})

    assert result["ok"] is True
    assert result["field_missing"] == []


def test_release_artifacts_required_by_verifier_exist():
    import os

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    required = [
        "docs/deployment.md",
        "docs/incident-playbook.md",
        "docs/production-checklist.md",
        "MAINTENANCE.md",
        ".github/workflows/release.yml",
        "examples/feishu_scenarios.json",
    ]

    assert all(os.path.isfile(os.path.join(repo, path)) for path in required)


def test_source_distribution_manifest_includes_release_audit_sources():
    import os

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    manifest = open(os.path.join(repo, "MANIFEST.in"), encoding="utf-8").read()
    required_terms = [
        "include README.zh-CN.md",
        "include SECURITY.md",
        "include MAINTENANCE.md",
        "include yinyo.env.example",
        "graft .github",
        "graft docs",
        "graft examples",
        "graft scripts",
        "graft tests",
        "prune workspace",
        "prune release-artifacts",
    ]

    for term in required_terms:
        assert term in manifest


def test_runtime_diagnostics_reports_failures_and_missing_smoke(tmp_path):
    from yinyo import JsonlEventStore, JsonlJobQueue, RuntimeLogger, RuntimeStoreLock, summarize_runtime

    logger = RuntimeLogger(str(tmp_path / "runtime.jsonl"))
    logger.record("webhook_rejected", correlation_id="evt_bad", reason="bad_verify_token")
    logger.record("outbox_delivery", correlation_id="evt_1", success=False, error="send failed", dead_letter=True, attempts=2)
    logger.record(
        "ws_event_received",
        correlation_id="evt_slow",
        ack_latency_ms=3100,
        ack_deadline_ms=3000,
        ack_within_deadline=False,
    )
    queue = JsonlJobQueue(str(tmp_path / "runtime_jobs.jsonl"))
    queue.enqueue("unit", {"value": 1}, lambda payload: (_ for _ in ()).throw(RuntimeError("boom")), run_async=False)
    event_store = JsonlEventStore(str(tmp_path / "gateway_events.jsonl"))
    event_store.mark_seen("evt_1")

    with RuntimeStoreLock(str(tmp_path / "yinyo_runtime.lock"), owner="active-service"):
        summary = summarize_runtime(
            log_path=str(tmp_path / "runtime.jsonl"),
            job_store_path=str(tmp_path / "runtime_jobs.jsonl"),
            smoke_evidence_path=str(tmp_path / "smoke_evidence.jsonl"),
            event_store_path=str(tmp_path / "gateway_events.jsonl"),
            runtime_lock_path=str(tmp_path / "yinyo_runtime.lock"),
        )

    assert summary["ok"] is False
    assert summary["runtime_lock"]["status"] == "locked"
    assert "active-service" in summary["runtime_lock"]["detail"]
    assert summary["runtime"]["event_counts"]["webhook_rejected"] == 1
    assert summary["event_store"]["unique_event_keys"] == 1
    assert summary["jobs"]["status_counts"]["failed"] == 1
    assert summary["runtime"]["service"]["started"] is False
    assert summary["runtime"]["service"]["last_status"] == "unknown"
    assert any("runtime job" in item for item in summary["alerts"])
    assert any("outbox delivery dead-letter" in item for item in summary["alerts"])
    assert summary["failures"]["outbox_dead_letter"][0]["attempts"] == 2
    assert any("ack deadline" in item for item in summary["alerts"])
    assert summary["failures"]["ack_deadline"][0]["ack_latency_ms"] == 3100
    assert summary["diagnosis"]["schema"] == "yinyo.trace_failure_diagnosis.v1"
    assert summary["diagnosis"]["root_cause"] == "ack_deadline_miss"
    assert summary["diagnosis"]["trace_complete"] is True
    assert any("live smoke evidence incomplete" in item for item in summary["alerts"])


def test_runtime_diagnostics_alerts_on_abandoned_jobs(tmp_path):
    import json
    import time
    from yinyo import JsonlEventStore, RuntimeLogger, SmokeEvidenceRecorder, summarize_runtime

    logger = RuntimeLogger(str(tmp_path / "runtime.jsonl"))
    logger.record("webhook_accepted", correlation_id="evt_1")
    job_path = tmp_path / "runtime_jobs.jsonl"
    created = time.time() - 30
    job_path.write_text(
        json.dumps({
            "id": "job_abandoned",
            "kind": "feishu_message",
            "payload": {"event_key": "evt_1"},
            "status": "abandoned",
            "created_at": created,
            "started_at": created,
            "finished_at": time.time(),
            "error": "job abandoned after runtime restart before completion",
            "event": "abandoned_after_restart",
            "recorded_at": time.time(),
        }) + "\n",
        encoding="utf-8",
    )
    event_store = JsonlEventStore(str(tmp_path / "gateway_events.jsonl"))
    event_store.mark_seen("evt_1")
    recorder = SmokeEvidenceRecorder(str(tmp_path / "smoke_evidence.jsonl"))

    summary = summarize_runtime(
        log_path=str(tmp_path / "runtime.jsonl"),
        job_store_path=str(job_path),
        smoke_evidence_path=recorder.path,
        event_store_path=str(tmp_path / "gateway_events.jsonl"),
        runtime_lock_path=str(tmp_path / "yinyo_runtime.lock"),
    )

    assert summary["jobs"]["status_counts"]["abandoned"] == 1
    assert any("runtime job(s) abandoned after restart" in alert for alert in summary["alerts"])


def test_runtime_diagnostics_alerts_on_backpressure_rejected_jobs(tmp_path):
    import json
    import time
    from yinyo import JsonlEventStore, RuntimeLogger, SmokeEvidenceRecorder, summarize_runtime

    logger = RuntimeLogger(str(tmp_path / "runtime.jsonl"))
    logger.record("webhook_accepted", correlation_id="evt_1")
    job_path = tmp_path / "runtime_jobs.jsonl"
    job_path.write_text(
        json.dumps({
            "id": "job_rejected",
            "kind": "feishu_message",
            "payload": {"event_key": "evt_1"},
            "status": "rejected",
            "created_at": time.time(),
            "finished_at": time.time(),
            "error": "job queue saturated",
            "event": "rejected_queue_saturated",
            "recorded_at": time.time(),
        }) + "\n",
        encoding="utf-8",
    )
    event_store = JsonlEventStore(str(tmp_path / "gateway_events.jsonl"))
    event_store.mark_seen("evt_1")
    recorder = SmokeEvidenceRecorder(str(tmp_path / "smoke_evidence.jsonl"))

    summary = summarize_runtime(
        log_path=str(tmp_path / "runtime.jsonl"),
        job_store_path=str(job_path),
        smoke_evidence_path=recorder.path,
        event_store_path=str(tmp_path / "gateway_events.jsonl"),
        runtime_lock_path=str(tmp_path / "yinyo_runtime.lock"),
    )

    assert summary["jobs"]["status_counts"]["rejected"] == 1
    assert any("runtime job(s) rejected by backpressure" in alert for alert in summary["alerts"])


def test_runtime_diagnostics_accepts_complete_smoke_and_successful_jobs(tmp_path):
    from yinyo import JsonlEventStore, JsonlJobQueue, RuntimeLogger, SmokeEvidenceRecorder, summarize_runtime
    from yinyo.smoke import REQUIRED_1_0_SCENARIOS

    logger = RuntimeLogger(str(tmp_path / "runtime.jsonl"))
    logger.record("service_start", correlation_id="service", profile="local", transport="ws")
    logger.record("service_stop", correlation_id="service", status="stopped", transport="ws")
    logger.record("webhook_accepted", correlation_id="evt_1", event_key="evt_1")
    logger.record(
        "ws_event_received",
        correlation_id="evt_1",
        ack_latency_ms=18.0,
        ack_deadline_ms=3000.0,
        ack_within_deadline=True,
    )
    logger.record("webhook_duplicate", correlation_id="evt_1", event_key="evt_1")
    logger.record("outbox_delivery", correlation_id="evt_1", success=True)
    queue = JsonlJobQueue(str(tmp_path / "runtime_jobs.jsonl"))
    queue.enqueue("feishu_message", {"event_key": "evt_1"}, lambda payload: {"ok": True}, run_async=False)
    event_store = JsonlEventStore(str(tmp_path / "gateway_events.jsonl"))
    event_store.mark_seen("evt_1")
    recorder = SmokeEvidenceRecorder(str(tmp_path / "smoke_evidence.jsonl"))
    for scenario in REQUIRED_1_0_SCENARIOS:
        recorder.record(scenario, "passed", live=True, event_key="evt_1")

    summary = summarize_runtime(
        log_path=str(tmp_path / "runtime.jsonl"),
        job_store_path=str(tmp_path / "runtime_jobs.jsonl"),
        smoke_evidence_path=str(tmp_path / "smoke_evidence.jsonl"),
        event_store_path=str(tmp_path / "gateway_events.jsonl"),
        runtime_lock_path=str(tmp_path / "yinyo_runtime.lock"),
    )

    assert summary["ok"] is True
    assert summary["alerts"] == []
    assert summary["runtime"]["ws"]["events"] == 1
    assert summary["runtime"]["ws"]["ack_deadline_misses"] == 0
    assert summary["runtime"]["ws"]["max_ack_latency_ms"] == 18.0
    assert summary["runtime"]["service"]["started"] is True
    assert summary["runtime"]["service"]["last_status"] == "stopped"
    assert summary["runtime"]["service"]["transport"] == "ws"
    assert summary["runtime_lock"]["status"] == "available"
    assert summary["event_store"]["last_event_key"] == "evt_1"
    assert summary["smoke"]["missing"] == []
    assert summary["correlation"]["ok"] is True
    assert summary["correlation"]["missing"] == []


def test_runtime_diagnostics_alerts_when_event_store_empty(tmp_path):
    from yinyo import JsonlJobQueue, RuntimeLogger, SmokeEvidenceRecorder, summarize_runtime
    from yinyo.smoke import REQUIRED_1_0_SCENARIOS

    logger = RuntimeLogger(str(tmp_path / "runtime.jsonl"))
    logger.record("webhook_accepted", correlation_id="evt_1", event_key="evt_1")
    queue = JsonlJobQueue(str(tmp_path / "runtime_jobs.jsonl"))
    queue.enqueue("unit", {"value": 1}, lambda payload: {"ok": True}, run_async=False)
    recorder = SmokeEvidenceRecorder(str(tmp_path / "smoke_evidence.jsonl"))
    for scenario in REQUIRED_1_0_SCENARIOS:
        recorder.record(scenario, "passed", live=True)

    summary = summarize_runtime(
        log_path=str(tmp_path / "runtime.jsonl"),
        job_store_path=str(tmp_path / "runtime_jobs.jsonl"),
        smoke_evidence_path=str(tmp_path / "smoke_evidence.jsonl"),
        event_store_path=str(tmp_path / "gateway_events.jsonl"),
        runtime_lock_path=str(tmp_path / "yinyo_runtime.lock"),
    )

    assert summary["ok"] is False
    assert summary["event_store"]["unique_event_keys"] == 0
    assert any("event store" in item for item in summary["alerts"])


def test_runtime_diagnostics_alerts_on_correlation_mismatch(tmp_path):
    from yinyo import JsonlEventStore, JsonlJobQueue, RuntimeLogger, SmokeEvidenceRecorder, summarize_runtime

    logger = RuntimeLogger(str(tmp_path / "runtime.jsonl"))
    logger.record("outbox_delivery", correlation_id="evt_wrong", event_key="evt_wrong", success=True)
    queue = JsonlJobQueue(str(tmp_path / "runtime_jobs.jsonl"))
    queue.enqueue("feishu_message", {"event_key": "evt_wrong"}, lambda payload: {"ok": True}, run_async=False)
    event_store = JsonlEventStore(str(tmp_path / "gateway_events.jsonl"))
    event_store.mark_seen("evt_wrong")
    recorder = SmokeEvidenceRecorder(str(tmp_path / "smoke_evidence.jsonl"))
    recorder.record("text_message_reply", "passed", live=True, event_key="evt_expected")

    summary = summarize_runtime(
        log_path=str(tmp_path / "runtime.jsonl"),
        job_store_path=str(tmp_path / "runtime_jobs.jsonl"),
        smoke_evidence_path=str(tmp_path / "smoke_evidence.jsonl"),
        event_store_path=str(tmp_path / "gateway_events.jsonl"),
        runtime_lock_path=str(tmp_path / "yinyo_runtime.lock"),
        transport="ws",
    )

    assert summary["ok"] is False
    assert "correlation:text_message_reply:runtime_log" in summary["correlation"]["missing"]
    assert any("correlation chain incomplete" in alert for alert in summary["alerts"])


def test_runtime_diagnostics_alerts_on_failed_service_stop(tmp_path):
    from yinyo import JsonlEventStore, JsonlJobQueue, RuntimeLogger, SmokeEvidenceRecorder, summarize_runtime
    from yinyo.smoke import REQUIRED_1_0_SCENARIOS

    logger = RuntimeLogger(str(tmp_path / "runtime.jsonl"))
    logger.record("service_start", correlation_id="service", profile="local", transport="ws")
    logger.record(
        "service_stop",
        correlation_id="service",
        status="failed",
        transport="ws",
        error_type="RuntimeError",
    )
    logger.record("webhook_accepted", correlation_id="evt_1", event_key="evt_1")
    logger.record(
        "ws_event_received",
        correlation_id="evt_1",
        ack_latency_ms=18.0,
        ack_deadline_ms=3000.0,
        ack_within_deadline=True,
    )
    logger.record("outbox_delivery", correlation_id="evt_1", success=True)
    queue = JsonlJobQueue(str(tmp_path / "runtime_jobs.jsonl"))
    queue.enqueue("unit", {"value": 1}, lambda payload: {"ok": True}, run_async=False)
    event_store = JsonlEventStore(str(tmp_path / "gateway_events.jsonl"))
    event_store.mark_seen("evt_1")
    recorder = SmokeEvidenceRecorder(str(tmp_path / "smoke_evidence.jsonl"))
    for scenario in REQUIRED_1_0_SCENARIOS:
        recorder.record(scenario, "passed", live=True)

    summary = summarize_runtime(
        log_path=str(tmp_path / "runtime.jsonl"),
        job_store_path=str(tmp_path / "runtime_jobs.jsonl"),
        smoke_evidence_path=str(tmp_path / "smoke_evidence.jsonl"),
        event_store_path=str(tmp_path / "gateway_events.jsonl"),
        runtime_lock_path=str(tmp_path / "yinyo_runtime.lock"),
    )

    assert summary["ok"] is False
    assert summary["runtime"]["service"]["last_status"] == "failed"
    assert summary["runtime"]["service"]["error_type"] == "RuntimeError"
    assert any("service exited with failure: RuntimeError" in item for item in summary["alerts"])


def test_cli_diagnose_json_reports_runtime_health(tmp_path):
    import subprocess
    import sys

    from yinyo import JsonlEventStore, JsonlJobQueue, RuntimeLogger, SmokeEvidenceRecorder
    from yinyo.smoke import REQUIRED_1_0_SCENARIOS

    logger = RuntimeLogger(str(tmp_path / "runtime.jsonl"))
    logger.record("service_start", correlation_id="service", profile="local", transport="ws")
    logger.record("service_stop", correlation_id="service", status="stopped", transport="ws")
    logger.record("webhook_accepted", correlation_id="evt_1", event_key="evt_1")
    logger.record("ws_event_received", correlation_id="evt_1", ack_latency_ms=18.0, ack_deadline_ms=3000.0, ack_within_deadline=True)
    logger.record("outbox_delivery", correlation_id="evt_1", success=True)
    logger.record("webhook_duplicate", correlation_id="evt_1", event_key="evt_1")
    queue = JsonlJobQueue(str(tmp_path / "runtime_jobs.jsonl"))
    queue.enqueue("feishu_message", {"event_key": "evt_1"}, lambda payload: {"ok": True}, run_async=False)
    event_store = JsonlEventStore(str(tmp_path / "gateway_events.jsonl"))
    event_store.mark_seen("evt_1")
    recorder = SmokeEvidenceRecorder(str(tmp_path / "smoke_evidence.jsonl"))
    for scenario in REQUIRED_1_0_SCENARIOS:
        recorder.record(scenario, "passed", live=True, event_key="evt_1")

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ)
    env["PYTHONPATH"] = repo + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [sys.executable, "-m", "yinyo.cli", "diagnose", "--workspace", str(tmp_path), "--json"],
        cwd=str(tmp_path),
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    data = json.loads(result.stdout)

    assert result.returncode == 0
    assert data["ok"] is True
    assert data["jobs"]["status_counts"]["succeeded"] == 1
    assert data["runtime"]["service"]["last_status"] == "stopped"
    assert data["runtime_lock"]["status"] == "available"


def test_cli_diagnose_text_reports_ws_ack_summary(tmp_path):
    import subprocess
    import sys

    from yinyo import JsonlEventStore, JsonlJobQueue, RuntimeLogger, SmokeEvidenceRecorder
    from yinyo.smoke import REQUIRED_1_0_SCENARIOS

    logger = RuntimeLogger(str(tmp_path / "runtime.jsonl"))
    logger.record("service_start", correlation_id="service", profile="local", transport="ws")
    logger.record("service_stop", correlation_id="service", status="stopped", transport="ws")
    logger.record(
        "ws_event_received",
        correlation_id="evt_1",
        ack_latency_ms=24.0,
        ack_deadline_ms=3000.0,
        ack_within_deadline=True,
    )
    logger.record("webhook_accepted", correlation_id="evt_1", event_key="evt_1")
    logger.record("outbox_delivery", correlation_id="evt_1", success=True)
    logger.record("webhook_duplicate", correlation_id="evt_1", event_key="evt_1")
    queue = JsonlJobQueue(str(tmp_path / "runtime_jobs.jsonl"))
    queue.enqueue("feishu_message", {"event_key": "evt_1"}, lambda payload: {"ok": True}, run_async=False)
    event_store = JsonlEventStore(str(tmp_path / "gateway_events.jsonl"))
    event_store.mark_seen("evt_1")
    recorder = SmokeEvidenceRecorder(str(tmp_path / "smoke_evidence.jsonl"))
    for scenario in REQUIRED_1_0_SCENARIOS:
        recorder.record(scenario, "passed", live=True, event_key="evt_1")

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ)
    env["PYTHONPATH"] = repo + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [sys.executable, "-m", "yinyo.cli", "diagnose", "--workspace", str(tmp_path)],
        cwd=str(tmp_path),
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )

    assert result.returncode == 0
    assert "YINYO diagnostics: OK" in result.stdout
    assert "service: started=True, last_status=stopped, transport=ws, error_type=" in result.stdout
    assert "ws events: 1, ack_misses: 0, max_ack_latency_ms: 24.0, ack_deadline_ms: 3000.0" in result.stdout
