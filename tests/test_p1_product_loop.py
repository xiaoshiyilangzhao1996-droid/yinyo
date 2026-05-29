# test_p1_product_loop.py — P1 product-loop acceptance checks from docs/spec.md

import json
import os


def test_file_changing_run_creates_manifest_from_real_trace(tmp_path):
    from yinyo import YinyoAgent

    workspace = tmp_path / "ws"
    workspace.mkdir()
    agent = YinyoAgent(workspace=str(workspace), max_steps=3)
    agent.model.set_mock_responses([
        {"content": "[STEP 1] write report", "finish_reason": "stop"},
        {
            "content": "",
            "tool_calls": [{
                "id": "call_write",
                "type": "function",
                "function": {
                    "name": "do_write",
                    "arguments": json.dumps({
                        "path": "report.md",
                        "content": "# Report",
                        "confirmation": {
                            "actor": "test-operator",
                            "scope": "do_write",
                            "reason": "manifest acceptance write",
                            "expires_at": "2099-01-01T00:00:00Z",
                        },
                    }),
                },
            }],
            "finish_reason": "tool_calls",
        },
        {"content": "done", "finish_reason": "stop"},
        {"content": '{"reflections": [], "memory_add": [], "memory_update": [], "memory_remove": []}', "finish_reason": "stop"},
        {"content": "[]", "finish_reason": "stop"},
        {"content": '{"change_type": "docs", "summary": "Write report file"}', "finish_reason": "stop"},
    ])

    result = agent.run("write report")

    manifest_path = workspace / "manifests" / f"{result['run_id']}.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["affected_files"] == ["report.md"]
    assert manifest["evidence_refs"]
    assert manifest["summary"] == "Write report file"


def test_blocked_file_change_does_not_create_file_change_manifest(tmp_path):
    from yinyo import YinyoAgent

    workspace = tmp_path / "ws"
    workspace.mkdir()
    agent = YinyoAgent(workspace=str(workspace), max_steps=3)
    agent.model.set_mock_responses([
        {"content": "[STEP 1] write blocked report", "finish_reason": "stop"},
        {
            "content": "",
            "tool_calls": [{
                "id": "call_write",
                "type": "function",
                "function": {
                    "name": "do_write",
                    "arguments": json.dumps({"path": "blocked.md", "content": "blocked"}),
                },
            }],
            "finish_reason": "tool_calls",
        },
        {"content": "done", "finish_reason": "stop"},
    ])

    result = agent.run("write blocked report")

    assert result["status"] == "partial"
    assert not (workspace / "manifests" / f"{result['run_id']}.json").exists()


def test_run_writes_structured_handoff_packet(tmp_path):
    from yinyo import YinyoAgent, replay_handoff

    workspace = tmp_path / "ws"
    workspace.mkdir()
    agent = YinyoAgent(workspace=str(workspace), max_steps=2)
    agent.model.set_mock_responses([
        {"content": "[STEP 1] answer", "finish_reason": "stop"},
        {"content": "done", "finish_reason": "stop"},
        {"content": '{"reflections": [], "memory_add": [], "memory_update": [], "memory_remove": []}', "finish_reason": "stop"},
        {"content": "[]", "finish_reason": "stop"},
    ])

    result = agent.run("prepare handoff evidence", correlation_id="corr-handoff")

    handoff_path = workspace / result["handoff_file"]
    manifest_path = workspace / "runs" / result["run_id"] / "manifest.json"
    assert handoff_path.is_file()
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert handoff["schema"] == "yinyo.handoff.v1"
    assert handoff["correlation_id"] == "corr-handoff"
    assert handoff["intent"]["original_task"] == "prepare handoff evidence"
    assert handoff["permissions"]["confirm_tools_require_structured_metadata"] is True
    assert handoff["provenance"]["model_usage"]["calls"] >= 0
    assert handoff["budget_state"]["max_steps"] == 2
    assert handoff["budget_state"]["steps_used"] + handoff["budget_state"]["steps_remaining"] == 2
    assert handoff["trace_history"]["correlation_id"] == "corr-handoff"
    assert isinstance(handoff["trace_history"]["evidence_hashes"], list)
    assert manifest["handoff"]["path"] == result["handoff_file"]
    resume = replay_handoff(handoff_path, workspace=workspace)
    assert resume["schema"] == "yinyo.handoff_resume.v1"
    assert resume["ok"] is True
    assert resume["resume_ready"] is True
    assert resume["resume_context"]["original_task"] == "prepare handoff evidence"
    assert resume["resume_context"]["permissions"]["confirm_tools_require_structured_metadata"] is True
    assert resume["resume_context"]["budget_state"]["max_steps"] == 2
    assert resume["resume_context"]["trace_history"]["correlation_id"] == "corr-handoff"
    assert resume["inherited"]["intent"]["original_task"] == "prepare handoff evidence"
    for key in ["intent", "constraints", "permissions", "artifacts", "provenance", "budget_state", "trace_history", "risk", "unresolved"]:
        assert key in resume["inherited"]
    assert all(resume["checks"][key] is True for key in ["intent", "constraints", "permissions", "artifacts", "provenance", "budget_state", "trace_history", "risk", "unresolved"])
    assert resume["checks"]["evidence_artifact"] is True
    assert resume["checks"]["manifest_artifact"] is True
    assert resume["checks"]["evidence_artifact_exists"] is True
    assert resume["checks"]["manifest_artifact_exists"] is True
    assert resume["checks"]["budget_recoverable"] is True
    assert resume["checks"]["trace_recoverable"] is True
    assert resume["resume_context"]["artifacts"]["exists"]["manifest_file"] is True


def test_handoff_replay_rejects_missing_artifact_fields(tmp_path):
    from yinyo import replay_handoff

    handoff_path = tmp_path / "runs" / "r1" / "handoff.json"
    handoff_path.parent.mkdir(parents=True)
    handoff_path.write_text(json.dumps({
        "schema": "yinyo.handoff.v1",
        "run_id": "r1",
        "correlation_id": "corr",
        "intent": {"original_task": "resume this", "final_status": "success"},
        "constraints": {"workspace": str(tmp_path), "max_steps": 2, "max_runtime_seconds": 120},
        "permissions": {"confirm_tools_require_structured_metadata": True},
        "artifacts": {},
        "provenance": {"source_audit": {}},
        "budget_state": {"max_steps": 2, "steps_used": 0, "steps_remaining": 2, "max_runtime_seconds": 120, "model_usage": {}},
        "trace_history": {"correlation_id": "corr", "evidence_hashes": [], "tools_used": [], "model_errors": []},
        "risk": {"risk_notes": []},
        "unresolved": [],
    }), encoding="utf-8")

    resume = replay_handoff(handoff_path, workspace=tmp_path)

    assert resume["ok"] is False
    assert "artifacts" in resume["blockers"]
    assert "evidence_artifact" in resume["blockers"]
    assert "manifest_artifact" in resume["blockers"]


def test_handoff_replay_rejects_missing_artifact_files(tmp_path):
    from yinyo import replay_handoff

    handoff_path = tmp_path / "runs" / "r1" / "handoff.json"
    handoff_path.parent.mkdir(parents=True)
    handoff_path.write_text(json.dumps({
        "schema": "yinyo.handoff.v1",
        "run_id": "r1",
        "correlation_id": "corr",
        "intent": {"original_task": "resume this", "final_status": "success"},
        "constraints": {"workspace": str(tmp_path), "max_steps": 2, "max_runtime_seconds": 120},
        "permissions": {"confirm_tools_require_structured_metadata": True},
        "artifacts": {"evidence_file": "runs/r1/evidence.jsonl", "manifest_file": "runs/r1/manifest.json"},
        "provenance": {"source_audit": {}},
        "budget_state": {"max_steps": 2, "steps_used": 0, "steps_remaining": 2, "max_runtime_seconds": 120, "model_usage": {}},
        "trace_history": {"correlation_id": "corr", "evidence_hashes": [], "tools_used": [], "model_errors": []},
        "risk": {"risk_notes": []},
        "unresolved": [],
    }), encoding="utf-8")

    resume = replay_handoff(handoff_path, workspace=tmp_path)

    assert resume["ok"] is False
    assert "evidence_artifact_exists" in resume["blockers"]
    assert "manifest_artifact_exists" in resume["blockers"]
    assert resume["resume_context"]["artifacts"]["exists"]["evidence_file"] is False
    assert resume["resume_context"]["artifacts"]["exists"]["manifest_file"] is False


def test_handoff_replay_rejects_unrecoverable_budget_and_trace(tmp_path):
    from yinyo import replay_handoff

    run_dir = tmp_path / "runs" / "r1"
    run_dir.mkdir(parents=True)
    (run_dir / "evidence.jsonl").write_text("", encoding="utf-8")
    (run_dir / "manifest.json").write_text("{}", encoding="utf-8")
    handoff_path = run_dir / "handoff.json"
    handoff_path.write_text(json.dumps({
        "schema": "yinyo.handoff.v1",
        "run_id": "r1",
        "correlation_id": "corr",
        "intent": {"original_task": "resume this", "final_status": "success"},
        "constraints": {"workspace": str(tmp_path), "max_steps": 2, "max_runtime_seconds": 120},
        "permissions": {"confirm_tools_require_structured_metadata": True},
        "artifacts": {"evidence_file": "runs/r1/evidence.jsonl", "manifest_file": "runs/r1/manifest.json"},
        "provenance": {"source_audit": {}},
        "budget_state": {"max_steps": 2, "steps_used": 2, "steps_remaining": 2, "max_runtime_seconds": 120, "model_usage": {}},
        "trace_history": {"correlation_id": "other-corr", "evidence_hashes": [], "tools_used": [], "model_errors": []},
        "risk": {"risk_notes": []},
        "unresolved": [],
    }), encoding="utf-8")

    resume = replay_handoff(handoff_path, workspace=tmp_path)

    assert resume["ok"] is False
    assert "budget_recoverable" in resume["blockers"]
    assert "trace_recoverable" in resume["blockers"]


def test_memory_extract_can_explicitly_supersede_old_fact(tmp_path):
    from yinyo import MemoryStore, ModelGateway

    store = MemoryStore(str(tmp_path))
    model = ModelGateway(api_key="")
    store.set_model(model)
    old = store.add_fact(
        "用户偏好简洁回复",
        category="Preferences",
        scopes={"user_id": "ou_1"},
        confidence=0.8,
        source_run_id="old-run",
    )
    model.set_mock_responses([
        {"content": json.dumps([{
            "content": "用户偏好极致精度回复",
            "category": "Preferences",
            "confidence": 0.95,
            "supersedes": old.id,
        }], ensure_ascii=False), "finish_reason": "stop"},
    ])

    store.extract_and_store([
        {"role": "user", "content": "以后请极致精度回复"},
    ], "new-run")

    active = store.search_memory("用户 偏好", scopes={"user_id": "ou_1"}, limit=5)
    assert not any(n.id == old.id for n in active)
    assert any("极致精度" in n.content for n in active)
    trail = store.tree.get_audit_trail(old.id)
    assert [n.status for n in trail] == ["superseded", "created"]


def test_reflection_rejects_invalid_memory_mutations(tmp_path):
    from yinyo import YinyoAgent

    workspace = tmp_path / "ws"
    workspace.mkdir()
    agent = YinyoAgent(workspace=str(workspace), max_steps=2)
    huge = "x" * 1000
    agent.model.set_mock_responses([
        {"content": "[STEP 1] answer", "finish_reason": "stop"},
        {"content": "done", "finish_reason": "stop"},
        {"content": json.dumps({
            "reflections": ["valid reflection", 123],
            "memory_add": ["", huge, {"bad": "shape"}],
            "memory_update": [{"old_text": "", "new_text": "bad"}, "bad"],
            "memory_remove": [huge],
        }), "finish_reason": "stop"},
        {"content": "[]", "finish_reason": "stop"},
    ])

    result = agent.run("simple task")

    memory_text = (workspace / "MEMORY.md").read_text(encoding="utf-8")
    changes_text = (workspace / "changes.jsonl").read_text(encoding="utf-8")
    assert result["status"] == "success"
    assert huge not in memory_text
    assert "reflection_rejected" in changes_text


def test_reflection_accepts_valid_memory_add(tmp_path):
    from yinyo import YinyoAgent

    workspace = tmp_path / "ws"
    workspace.mkdir()
    agent = YinyoAgent(workspace=str(workspace), max_steps=2)
    agent.model.set_mock_responses([
        {"content": "[STEP 1] answer", "finish_reason": "stop"},
        {"content": "done", "finish_reason": "stop"},
        {"content": json.dumps({
            "reflections": ["learned a useful preference"],
            "memory_add": ["用户偏好简洁但准确的回复"],
            "memory_update": [],
            "memory_remove": [],
        }, ensure_ascii=False), "finish_reason": "stop"},
        {"content": "[]", "finish_reason": "stop"},
    ])

    agent.run("remember a preference")

    memory_text = (workspace / "MEMORY.md").read_text(encoding="utf-8")
    assert "用户偏好简洁但准确的回复" in memory_text


def test_extracted_memory_rejects_ephemeral_run_logs(tmp_path):
    from yinyo import MemoryStore, ModelGateway

    store = MemoryStore(str(tmp_path))
    model = ModelGateway(api_key="")
    store.set_model(model)
    model.set_mock_responses([
        {"content": json.dumps([
            {
                "content": "The assistant answered hello during this run.",
                "category": "General",
                "confidence": 0.9,
                "supersedes": None,
            },
            {
                "content": "User prefers concise release status updates with concrete blockers.",
                "category": "Preferences",
                "confidence": 0.9,
                "supersedes": None,
            },
        ]), "finish_reason": "stop"},
    ])

    result = store.extract_and_store([
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hello"},
    ], "run-1")

    active = store.tree.get_active_nodes()
    assert result["stored"] == 1
    assert result["rejected"] == 1
    assert result["reasons"] == ["ephemeral_content"]
    assert [node.content for node in active] == [
        "User prefers concise release status updates with concrete blockers."
    ]


def test_agent_records_rejected_extracted_memory(tmp_path):
    from yinyo import YinyoAgent

    workspace = tmp_path / "ws"
    workspace.mkdir()
    agent = YinyoAgent(workspace=str(workspace), max_steps=2)
    agent.model.set_mock_responses([
        {"content": "[STEP 1] answer", "finish_reason": "stop"},
        {"content": "hello", "finish_reason": "stop"},
        {"content": '{"reflections": [], "memory_add": [], "memory_update": [], "memory_remove": []}', "finish_reason": "stop"},
        {"content": json.dumps([{
            "content": "The assistant answered hello during this run.",
            "category": "General",
            "confidence": 0.9,
            "supersedes": None,
        }]), "finish_reason": "stop"},
    ])

    result = agent.run("say hello")

    changes_text = (workspace / "changes.jsonl").read_text(encoding="utf-8")
    assert result["status"] == "success"
    assert "memory_fact_rejected" in changes_text
    assert "ephemeral_content" in changes_text


def test_provider_fallback_is_observable_in_result_and_changes(tmp_path):
    from yinyo import YinyoAgent

    workspace = tmp_path / "ws"
    workspace.mkdir()
    agent = YinyoAgent(workspace=str(workspace), max_steps=2, api_key="test-key")
    agent.model.set_provider_mock_responses([
        {"content": "[STEP 1] answer", "finish_reason": "stop"},
        {"error": "flash unavailable"},
        {"content": "done after fallback", "finish_reason": "stop"},
        {"content": '{"reflections": [], "memory_add": [], "memory_update": [], "memory_remove": []}', "finish_reason": "stop"},
        {"content": "[]", "finish_reason": "stop"},
    ])

    result = agent.run("use fallback")

    changes_text = (workspace / "changes.jsonl").read_text(encoding="utf-8")
    assert result["fallbacks"]
    assert result["fallbacks"][0]["from"] == "deepseek-v4-flash"
    assert "model_fallback" in changes_text


def test_model_exhaustion_is_explicit_and_redacted(tmp_path):
    from yinyo import YinyoAgent

    workspace = tmp_path / "ws"
    workspace.mkdir()
    agent = YinyoAgent(workspace=str(workspace), max_steps=2, api_key="test-key")
    agent.model.set_mock_responses([
        {"content": "[STEP 1] answer", "finish_reason": "stop"},
        {"error": "timeout api_key='sk-secret-secret-secret-secret'"},
        {"error": "rate limited token=super-secret-token"},
        {"content": '{"reflections": [], "memory_add": [], "memory_update": [], "memory_remove": []}', "finish_reason": "stop"},
        {"content": "[]", "finish_reason": "stop"},
    ])

    result = agent.run("handle model outage")

    changes_text = (workspace / "changes.jsonl").read_text(encoding="utf-8")
    assert result["status"] == "model_error"
    assert result["model_errors"]
    assert "model_error" in changes_text
    assert "sk-secret" not in changes_text
    assert "super-secret-token" not in changes_text


def test_external_fact_answer_without_source_is_not_success(tmp_path):
    from yinyo import YinyoAgent

    workspace = tmp_path / "ws"
    workspace.mkdir()
    agent = YinyoAgent(workspace=str(workspace), max_steps=2)
    agent.model.set_mock_responses([
        {"content": "[STEP 1] answer", "finish_reason": "stop"},
        {"content": "The latest price is 123.", "finish_reason": "stop"},
        {"content": '{"reflections": [], "memory_add": [], "memory_update": [], "memory_remove": []}', "finish_reason": "stop"},
        {"content": "[]", "finish_reason": "stop"},
    ])

    result = agent.run("What is the latest stock price?")

    changes_text = (workspace / "changes.jsonl").read_text(encoding="utf-8")
    assert result["status"] == "source_required"
    assert result["source_audit"] == {
        "required": True,
        "satisfied": False,
        "reason": "external_or_current_fact",
    }
    assert "source_required" in changes_text


def test_external_fact_answer_with_source_can_succeed(tmp_path):
    from yinyo import YinyoAgent

    workspace = tmp_path / "ws"
    workspace.mkdir()
    agent = YinyoAgent(workspace=str(workspace), max_steps=2)
    agent.model.set_mock_responses([
        {"content": "[STEP 1] answer", "finish_reason": "stop"},
        {"content": "The latest price is 123. Source: https://example.com/quote", "finish_reason": "stop"},
        {"content": '{"reflections": [], "memory_add": [], "memory_update": [], "memory_remove": []}', "finish_reason": "stop"},
        {"content": "[]", "finish_reason": "stop"},
    ])

    result = agent.run("What is the latest stock price?")

    assert result["status"] == "success"
    assert result["source_audit"]["required"] is True
    assert result["source_audit"]["satisfied"] is True


def test_handle_message_replaces_unsourced_external_answer_with_user_visible_prompt(tmp_path):
    from yinyo import YinyoAgent

    workspace = tmp_path / "ws"
    workspace.mkdir()
    agent = YinyoAgent(workspace=str(workspace), max_steps=2)
    agent.model.set_mock_responses([
        {"content": "[STEP 1] answer", "finish_reason": "stop"},
        {"content": "The latest stock price is 123.", "finish_reason": "stop"},
        {"content": '{"reflections": [], "memory_add": [], "memory_update": [], "memory_remove": []}', "finish_reason": "stop"},
        {"content": "[]", "finish_reason": "stop"},
    ])

    result = agent.handle_message("ou_1", "oc_1", "What is the latest stock price?")

    assert result["text"].startswith("I need a cited source")
    assert "123" not in result["text"]


def test_handle_message_replaces_partial_result_with_user_visible_failure(tmp_path):
    from yinyo import YinyoAgent

    workspace = tmp_path / "ws"
    workspace.mkdir()
    agent = YinyoAgent(workspace=str(workspace), max_steps=2)
    agent.model.set_mock_responses([
        {"content": "[STEP 1] write file", "finish_reason": "stop"},
        {
            "content": "",
            "tool_calls": [{
                "id": "call_write",
                "type": "function",
                "function": {
                    "name": "do_write",
                    "arguments": json.dumps({"path": "blocked.md", "content": "blocked"}),
                },
            }],
            "finish_reason": "tool_calls",
        },
        {"content": "done", "finish_reason": "stop"},
        {"content": '{"reflections": [], "memory_add": [], "memory_update": [], "memory_remove": []}', "finish_reason": "stop"},
        {"content": "[]", "finish_reason": "stop"},
    ])

    result = agent.handle_message("ou_1", "oc_1", "write a file")

    assert result["text"].startswith("I completed only part")
    assert "done" not in result["text"]


def test_handle_message_replaces_model_error_with_user_visible_failure(tmp_path):
    from yinyo import YinyoAgent

    workspace = tmp_path / "ws"
    workspace.mkdir()
    agent = YinyoAgent(workspace=str(workspace), max_steps=2, api_key="test-key")
    agent.model.set_mock_responses([
        {"content": "[STEP 1] answer", "finish_reason": "stop"},
        {"error": "timeout token=secret-token"},
        {"error": "rate limit token=secret-token"},
        {"content": '{"reflections": [], "memory_add": [], "memory_update": [], "memory_remove": []}', "finish_reason": "stop"},
        {"content": "[]", "finish_reason": "stop"},
    ])

    result = agent.handle_message("ou_1", "oc_1", "answer")

    assert result["text"].startswith("I could not complete this because the model provider failed")
    assert "secret-token" not in result["text"]


class _FakeSessionManager:
    def is_duplicate(self, text, user_id):
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
        return {"text": "ok", "files": [], "run_id": "run-fake"}


def test_feishu_url_verification_checks_token():
    from yinyo.feishu_adapter import FeishuAdapter

    adapter = FeishuAdapter(agent=None, config={"verify_token": "good-token"})

    assert adapter.handle_webhook_event({
        "type": "url_verification",
        "token": "bad-token",
        "challenge": "abc",
    }, async_dispatch=False) == (403, {})
    assert adapter.handle_webhook_event({
        "type": "url_verification",
        "token": "good-token",
        "challenge": "abc",
    }, async_dispatch=False) == (200, {"challenge": "abc"})


def test_feishu_text_event_routes_to_agent(monkeypatch):
    from yinyo.feishu_adapter import FeishuAdapter

    agent = _FakeAgent()
    adapter = FeishuAdapter(agent=agent, config={"verify_token": "good-token"})
    monkeypatch.setattr(adapter, "add_reaction", lambda *args, **kwargs: True)
    monkeypatch.setattr(adapter, "remove_reaction", lambda *args, **kwargs: True)
    sent = []
    monkeypatch.setattr(adapter, "send_message", lambda *args, **kwargs: sent.append((args, kwargs)) or {"success": True})

    code, body = adapter.handle_webhook_event({
        "type": "event_callback",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": "<at user_id=\"ou_bot\">Bot</at> hello"}),
                "chat_id": "oc_1",
                "message_id": "om_1",
            },
        },
    }, async_dispatch=False)

    assert (code, body) == (200, {})
    assert agent.messages[0]["text"] == "@open_id:ou_bot hello"
    assert agent.messages[0]["already_deduped"] is True
    assert agent.messages[0]["correlation_id"] == "om_1"
    assert sent


def test_feishu_text_agent_exception_reply_is_generic(monkeypatch):
    from yinyo.feishu_adapter import FeishuAdapter

    class FailingAgent(_FakeAgent):
        def handle_message(self, *args, **kwargs):
            raise RuntimeError("secret sk-http-token should not reach chat")

    agent = FailingAgent()
    adapter = FeishuAdapter(agent=agent, config={"verify_token": "good-token"})
    monkeypatch.setattr(adapter, "add_reaction", lambda *args, **kwargs: True)
    monkeypatch.setattr(adapter, "remove_reaction", lambda *args, **kwargs: True)
    sent = []
    monkeypatch.setattr(adapter, "send_message", lambda *args, **kwargs: sent.append((args, kwargs)) or {"success": True})

    code, body = adapter.handle_webhook_event({
        "type": "event_callback",
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

    assert (code, body) == (200, {})
    sent_text = sent[0][0][1]
    assert "could not complete" in sent_text
    assert "sk-http-token" not in sent_text


def test_feishu_bad_event_token_is_rejected():
    from yinyo.feishu_adapter import FeishuAdapter

    agent = _FakeAgent()
    adapter = FeishuAdapter(agent=agent, config={"verify_token": "good-token"})

    code, body = adapter.handle_webhook_event({
        "type": "event_callback",
        "token": "bad-token",
        "event": {"message": {"message_type": "text"}},
    }, async_dispatch=False)

    assert (code, body) == (403, {})
    assert agent.messages == []


def test_feishu_image_event_routes_vision_text(monkeypatch):
    from yinyo.feishu_adapter import FeishuAdapter

    agent = _FakeAgent()
    adapter = FeishuAdapter(agent=agent, config={"verify_token": "good-token"})
    monkeypatch.setattr(adapter, "_download_image", lambda image_key: "local.png")
    monkeypatch.setattr(adapter, "add_reaction", lambda *args, **kwargs: True)
    monkeypatch.setattr(adapter, "remove_reaction", lambda *args, **kwargs: True)
    monkeypatch.setattr(adapter, "send_message", lambda *args, **kwargs: {"success": True})
    prompts = []

    class FakeVision:
        def describe(self, image_path, query):
            prompts.append(query)
            return {"description": f"described {image_path}", "error": None}

    import yinyo.vision_adapter as vision_adapter
    monkeypatch.setattr(vision_adapter, "get_vision_adapter", lambda: FakeVision())

    code, body = adapter.handle_webhook_event({
        "type": "event_callback",
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "image",
                "content": json.dumps({"image_key": "img_123"}),
                "chat_id": "oc_1",
                "message_id": "om_1",
            },
        },
    }, async_dispatch=False)

    assert (code, body) == (200, {})
    assert "[Image message received]" in agent.messages[0]["text"]
    assert "described local.png" in agent.messages[0]["text"]
    assert prompts == ["Describe the image contents in detail."]
    prompts[0].encode("ascii")
