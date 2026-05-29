# test_p3_gateway.py — P3 Feishu runtime gateway acceptance checks

import json


class _FakeSessionManager:
    def __init__(self):
        self.seen = set()

    def is_duplicate(self, text, user_id):
        key = (text, user_id)
        if key in self.seen:
            return True
        self.seen.add(key)
        return False


class _FakeAgent:
    def __init__(self):
        self.session_manager = _FakeSessionManager()
        self.messages = []

    def handle_message(self, user_id, chat_id, text, already_deduped=False, correlation_id=""):
        self.messages.append({
            "user_id": user_id,
            "chat_id": chat_id,
            "text": text,
            "already_deduped": already_deduped,
            "correlation_id": correlation_id,
        })
        return {"text": "reply", "files": [], "run_id": "run-fake"}


class _FakeAdapter:
    def __init__(self, agent=None):
        self.agent = agent
        self.reactions = []
        self.removed = []
        self.sent = []

    def add_reaction(self, message_id):
        self.reactions.append(message_id)
        return True

    def remove_reaction(self, message_id):
        self.removed.append(message_id)
        return True

    def send_message(self, chat_id, text, reply_to=None, files=None):
        self.sent.append({
            "chat_id": chat_id,
            "text": text,
            "reply_to": reply_to,
            "files": files or [],
        })
        return {"success": True, "message_ids": ["om_reply"], "fallback": False}

    def _download_image(self, image_key):
        return f"{image_key}.png"


def _text_event(uuid="evt_1", message_id="om_1", token="good-token"):
    return {
        "type": "event_callback",
        "uuid": uuid,
        "token": token,
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": '<at user_id="ou_bot">Bot</at> hello'}),
                "chat_id": "oc_1",
                "message_id": message_id,
            },
        },
    }


def test_gateway_fast_ack_enqueues_without_inline_agent_execution():
    from yinyo import FeishuRuntimeGateway, RuntimeJob

    agent = _FakeAgent()
    adapter = _FakeAdapter(agent)

    class RecordingQueue:
        def __init__(self):
            self.jobs = {}
            self.run_async_values = []

        def enqueue(self, kind, payload, handler, *, run_async=True):
            self.run_async_values.append(run_async)
            job = RuntimeJob(id="job_recorded", kind=kind, payload=payload)
            self.jobs[job.id] = job
            return job

        def get(self, job_id):
            return self.jobs.get(job_id)

    queue = RecordingQueue()
    gateway = FeishuRuntimeGateway(
        adapter=adapter,
        agent=agent,
        verify_token="good-token",
        queue=queue,
    )

    result = gateway.handle_event(_text_event(), async_dispatch=True)

    assert result.status_code == 200
    assert result.body == {}
    assert result.job_id
    assert agent.messages == []
    assert queue.run_async_values == [True]
    assert gateway.get_job(result.job_id).kind == "feishu_message"


def test_gateway_synchronous_job_tracks_result_and_uses_outbox():
    from yinyo import FeishuRuntimeGateway

    agent = _FakeAgent()
    adapter = _FakeAdapter(agent)
    gateway = FeishuRuntimeGateway(adapter=adapter, agent=agent, verify_token="good-token")

    result = gateway.handle_event(_text_event(), async_dispatch=False)
    job = gateway.get_job(result.job_id)

    assert result.status_code == 200
    assert job.status == "succeeded"
    assert job.started_at is not None
    assert job.finished_at is not None
    assert job.result["ok"] is True
    assert agent.messages[0]["text"] == "@open_id:ou_bot hello"
    assert agent.messages[0]["already_deduped"] is True
    assert agent.messages[0]["correlation_id"] == "evt_1"
    assert adapter.reactions == ["om_1"]
    assert adapter.removed == ["om_1"]
    assert adapter.sent[0]["reply_to"] == "om_1"


def test_gateway_outbox_retries_before_dead_letter():
    from yinyo import FeishuRuntimeGateway

    class FlakyAdapter(_FakeAdapter):
        def send_message(self, chat_id, text, reply_to=None, files=None, force_fallback=False):
            self.sent.append({"chat_id": chat_id, "text": text, "reply_to": reply_to, "files": files or []})
            if len(self.sent) == 1:
                return {"success": False, "message_ids": [], "error": "temporary send failure"}
            return {"success": True, "message_ids": ["om_retry"], "fallback": False}

    agent = _FakeAgent()
    adapter = FlakyAdapter(agent)
    gateway = FeishuRuntimeGateway(adapter=adapter, agent=agent, verify_token="good-token")

    result = gateway.handle_event(_text_event(), async_dispatch=False)
    job = gateway.get_job(result.job_id)

    assert len(adapter.sent) == 2
    assert job.result["ok"] is True
    assert job.result["attempts"] == 2
    assert job.result["dead_letter"] is False
    assert job.result["message_ids"] == ["om_retry"]


def test_gateway_outbox_dead_letters_after_retry_exhaustion():
    from yinyo import FeishuRuntimeGateway

    class FailingAdapter(_FakeAdapter):
        def send_message(self, chat_id, text, reply_to=None, files=None, force_fallback=False):
            self.sent.append({"chat_id": chat_id, "text": text, "reply_to": reply_to, "files": files or []})
            return {"success": False, "message_ids": [], "error": "send failed"}

    agent = _FakeAgent()
    adapter = FailingAdapter(agent)
    gateway = FeishuRuntimeGateway(adapter=adapter, agent=agent, verify_token="good-token")

    result = gateway.handle_event(_text_event(), async_dispatch=False)
    job = gateway.get_job(result.job_id)

    assert len(adapter.sent) == 2
    assert job.result["ok"] is False
    assert job.result["attempts"] == 2
    assert job.result["dead_letter"] is True
    assert job.result["error"] == "send failed"


def test_gateway_outbox_errors_are_redacted_before_runtime_evidence(tmp_path):
    from yinyo import FeishuRuntimeGateway, SmokeEvidenceRecorder

    class LeakyAdapter(_FakeAdapter):
        def send_message(self, chat_id, text, reply_to=None, files=None, force_fallback=False):
            self.sent.append({"chat_id": chat_id, "text": text, "reply_to": reply_to, "files": files or []})
            return {
                "success": False,
                "message_ids": [],
                "error": "send failed api_key=sk-proj-abcdefghijklmnopqrstuvwxyz123456 tenant_access_token=secret-token-value",
            }

    class Logger:
        def __init__(self):
            self.records = []

        def record(self, event, **fields):
            self.records.append({"event": event, **fields})

    agent = _FakeAgent()
    logger = Logger()
    smoke_path = tmp_path / "smoke.jsonl"
    gateway = FeishuRuntimeGateway(
        adapter=LeakyAdapter(agent),
        agent=agent,
        verify_token="good-token",
        logger=logger,
        smoke_recorder=SmokeEvidenceRecorder(str(smoke_path)),
    )

    result = gateway.handle_event(_text_event(uuid="evt_secret_outbox"), async_dispatch=False)
    job = gateway.get_job(result.job_id)
    combined = json.dumps({
        "job": job.result,
        "logs": logger.records,
        "smoke": smoke_path.read_text(encoding="utf-8"),
    }, ensure_ascii=False)

    assert job.result["ok"] is False
    assert job.result["dead_letter"] is True
    assert "[REDACTED]" in combined
    assert "sk-proj-abcdefghijklmnopqrstuvwxyz123456" not in combined
    assert "secret-token-value" not in combined


def test_gateway_outbox_exception_errors_are_redacted(tmp_path):
    from yinyo import FeishuRuntimeGateway, SmokeEvidenceRecorder

    class ExplodingAdapter(_FakeAdapter):
        def send_message(self, chat_id, text, reply_to=None, files=None, force_fallback=False):
            raise RuntimeError("boom Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abcdefghijklmnop")

    agent = _FakeAgent()
    smoke_path = tmp_path / "smoke.jsonl"
    gateway = FeishuRuntimeGateway(
        adapter=ExplodingAdapter(agent),
        agent=agent,
        verify_token="good-token",
        smoke_recorder=SmokeEvidenceRecorder(str(smoke_path)),
    )

    result = gateway.handle_event(_text_event(uuid="evt_secret_exception"), async_dispatch=False)
    job = gateway.get_job(result.job_id)
    combined = json.dumps({"job": job.result, "smoke": smoke_path.read_text(encoding="utf-8")}, ensure_ascii=False)

    assert job.result["ok"] is False
    assert "[REDACTED]" in combined
    assert "eyJhbGciOiJIUzI1NiJ9.abcdefghijklmnop" not in combined


def test_gateway_rejects_bad_token_before_enqueue():
    from yinyo import FeishuRuntimeGateway

    agent = _FakeAgent()
    gateway = FeishuRuntimeGateway(
        adapter=_FakeAdapter(agent),
        agent=agent,
        verify_token="good-token",
    )

    result = gateway.handle_event(_text_event(token="bad-token"), async_dispatch=False)

    assert result.status_code == 403
    assert result.job_id is None
    assert agent.messages == []


def test_gateway_idempotency_blocks_duplicate_event_jobs():
    from yinyo import FeishuRuntimeGateway

    agent = _FakeAgent()
    gateway = FeishuRuntimeGateway(
        adapter=_FakeAdapter(agent),
        agent=agent,
        verify_token="good-token",
    )

    first = gateway.handle_event(_text_event(uuid="evt_dup"), async_dispatch=False)
    second = gateway.handle_event(_text_event(uuid="evt_dup"), async_dispatch=False)

    assert first.job_id
    assert second.status_code == 200
    assert second.duplicate is True
    assert second.job_id is None
    assert len(agent.messages) == 1


def test_gateway_backpressure_rejects_without_marking_event_seen():
    from yinyo import FeishuRuntimeGateway, RuntimeJob

    agent = _FakeAgent()

    class SaturatedQueue:
        def __init__(self):
            self.jobs = {}

        def enqueue(self, kind, payload, handler, *, run_async=True):
            job = RuntimeJob(id="job_rejected", kind=kind, payload=payload, status="rejected")
            job.error = "job queue saturated"
            self.jobs[job.id] = job
            return job

        def get(self, job_id):
            return self.jobs.get(job_id)

    gateway = FeishuRuntimeGateway(
        adapter=_FakeAdapter(agent),
        agent=agent,
        verify_token="good-token",
        queue=SaturatedQueue(),
    )

    result = gateway.handle_event(_text_event(uuid="evt_backpressure"), async_dispatch=True)

    assert result.status_code == 503
    assert result.body == {"error": "queue_saturated"}
    assert result.job_id == "job_rejected"
    assert "evt_backpressure" not in gateway._seen_event_keys
    assert agent.messages == []


def test_gateway_agent_exception_reply_is_generic_and_logs_type():
    from yinyo import FeishuRuntimeGateway

    class FailingAgent(_FakeAgent):
        def handle_message(self, *args, **kwargs):
            raise RuntimeError("secret sk-live-token should not reach chat")

    class Logger:
        def __init__(self):
            self.records = []

        def record(self, event, **fields):
            self.records.append({"event": event, **fields})

    agent = FailingAgent()
    adapter = _FakeAdapter(agent)
    logger = Logger()
    gateway = FeishuRuntimeGateway(
        adapter=adapter,
        agent=agent,
        verify_token="good-token",
        logger=logger,
    )

    result = gateway.handle_event(_text_event(uuid="evt_agent_failure"), async_dispatch=False)
    job = gateway.get_job(result.job_id)

    assert result.status_code == 200
    assert job.status == "succeeded"
    sent_text = adapter.sent[0]["text"]
    assert "could not complete" in sent_text
    assert "sk-live-token" not in sent_text
    failure_log = next(record for record in logger.records if record["event"] == "agent_message_failed")
    assert failure_log["error_type"] == "RuntimeError"
    assert "sk-live-token" not in json.dumps(logger.records, ensure_ascii=False)


def test_gateway_image_prompt_is_ascii_and_descriptive(monkeypatch):
    import yinyo.vision_adapter
    from yinyo import FeishuRuntimeGateway

    prompts = []

    class VisionAdapter:
        def describe(self, image_path, prompt):
            prompts.append(prompt)
            return {"description": "image description"}

    monkeypatch.setattr(yinyo.vision_adapter, "get_vision_adapter", lambda: VisionAdapter())
    agent = _FakeAgent()
    adapter = _FakeAdapter(agent)
    gateway = FeishuRuntimeGateway(adapter=adapter, agent=agent, verify_token="good-token")
    event = _text_event(uuid="evt_image_prompt")
    event["event"]["message"]["message_type"] = "image"
    event["event"]["message"]["content"] = json.dumps({"image_key": "img_prompt"})

    gateway.handle_event(event, async_dispatch=False)

    assert prompts == ["Describe the image contents in detail."]
    prompts[0].encode("ascii")
    assert "image description" in agent.messages[0]["text"]


def test_feishu_adapter_delegates_webhook_to_gateway(monkeypatch):
    from yinyo.feishu_adapter import FeishuAdapter

    agent = _FakeAgent()
    adapter = FeishuAdapter(agent=agent, config={"verify_token": "good-token"})
    monkeypatch.setattr(adapter, "add_reaction", lambda *args, **kwargs: True)
    monkeypatch.setattr(adapter, "remove_reaction", lambda *args, **kwargs: True)
    monkeypatch.setattr(adapter, "send_message", lambda *args, **kwargs: {"success": True, "message_ids": ["om_reply"]})

    code, body = adapter.handle_webhook_event(_text_event(), async_dispatch=False)

    assert (code, body) == (200, {})
    assert "evt_1" in adapter.gateway._seen_event_keys
    assert agent.messages[0]["text"] == "@open_id:ou_bot hello"
