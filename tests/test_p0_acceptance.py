# test_p0_acceptance.py — P0 acceptance checks from docs/spec.md

import json
import os


def test_package_import_and_agent_workspace_tools(tmp_path):
    import yinyo
    from yinyo.tools import do_read, do_search

    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "probe.txt").write_text("workspace data", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside data", encoding="utf-8")

    yinyo.YinyoAgent(workspace=str(workspace), max_steps=1)

    result = do_read("probe.txt")
    assert "workspace data" in result["content"]
    assert "Absolute paths not allowed" in do_read(str(outside))["error"]
    assert "Path traversal blocked" in do_read("../outside.txt")["error"]
    assert "Path traversal blocked" in do_search("outside", path="..")["error"]


def test_agent_loop_blocks_unconfirmed_confirm_tool(tmp_path):
    from yinyo import YinyoAgent

    workspace = tmp_path / "ws"
    workspace.mkdir()
    agent = YinyoAgent(workspace=str(workspace), max_steps=3)
    agent.model.set_mock_responses([
        {"content": "[STEP 1] write output", "finish_reason": "stop"},
        {
            "content": "",
            "tool_calls": [{
                "id": "call_write",
                "type": "function",
                "function": {
                    "name": "do_write",
                    "arguments": json.dumps({"path": "out.txt", "content": "api_key=sk-projABCDEFGHIJKLMNOPQRSTUVWXYZ"}),
                },
            }],
            "finish_reason": "tool_calls",
        },
        {"content": "done", "finish_reason": "stop"},
    ])

    result = agent.run("write a file")

    assert result["status"] == "partial"
    assert not (workspace / "out.txt").exists()
    evidence = workspace / result["evidence_file"]
    assert evidence.is_file()
    evidence_text = evidence.read_text(encoding="utf-8")
    assert "Confirmation required" in evidence_text
    assert "sk-proj" not in evidence_text


def test_confirmed_write_generates_manifest_and_utf8(tmp_path):
    from yinyo import YinyoAgent

    workspace = tmp_path / "ws"
    workspace.mkdir()
    agent = YinyoAgent(workspace=str(workspace), max_steps=3)
    agent.model.set_mock_responses([
        {"content": "[STEP 1] write unicode output", "finish_reason": "stop"},
        {
            "content": "",
            "tool_calls": [{
                "id": "call_write",
                "type": "function",
                "function": {
                    "name": "do_write",
                    "arguments": json.dumps({
                        "path": "out.txt",
                        "content": "你好 🌍",
                        "confirmation": {
                            "actor": "test-operator",
                            "scope": "do_write",
                            "reason": "acceptance test write",
                            "expires_at": "2099-01-01T00:00:00Z",
                        },
                    }, ensure_ascii=False),
                },
            }],
            "finish_reason": "tool_calls",
        },
        {"content": "done", "finish_reason": "stop"},
        {"content": '{"reflections": [], "memory_add": [], "memory_update": [], "memory_remove": []}', "finish_reason": "stop"},
        {"content": "[]", "finish_reason": "stop"},
        {"content": '{"change_type": "feat", "summary": "Write unicode output"}', "finish_reason": "stop"},
    ])

    result = agent.run("写入 Unicode 文件 🌍")

    assert result["status"] == "success"
    assert (workspace / "out.txt").read_text(encoding="utf-8") == "你好 🌍"
    manifest_path = workspace / "runs" / result["run_id"] / "manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["task"] == "写入 Unicode 文件 🌍"
    assert (workspace / "changes.jsonl").read_text(encoding="utf-8")
    assert (workspace / "MEMORY.md").read_text(encoding="utf-8")


def test_governance_block_writes_evidence(tmp_path):
    from yinyo import YinyoAgent

    workspace = tmp_path / "ws"
    workspace.mkdir()
    agent = YinyoAgent(workspace=str(workspace), max_steps=3)
    agent.model.set_mock_responses([
        {"content": "[STEP 1] try blocked command", "finish_reason": "stop"},
        {
            "content": "",
            "tool_calls": [{
                "id": "call_run",
                "type": "function",
                "function": {
                    "name": "do_run",
                    "arguments": json.dumps({
                        "command": "rm -rf /",
                        "confirmation": {
                            "actor": "test-operator",
                            "scope": "do_run",
                            "reason": "verify dangerous command block",
                            "expires_at": "2099-01-01T00:00:00Z",
                        },
                    }),
                },
            }],
            "finish_reason": "tool_calls",
        },
        {"content": "done", "finish_reason": "stop"},
    ])

    result = agent.run("run a dangerous command")

    assert result["status"] == "partial"
    evidence_text = (workspace / result["evidence_file"]).read_text(encoding="utf-8")
    assert "Blocked by risk policy" in evidence_text


def test_delegate_task_reaches_parent_agent(tmp_path):
    from yinyo import YinyoAgent
    from yinyo.tools import delegate_task

    workspace = tmp_path / "ws"
    workspace.mkdir()
    agent = YinyoAgent(workspace=str(workspace), max_steps=1)
    agent.model.set_mock_responses([
        {"content": "worker complete", "finish_reason": "stop"},
    ])

    result = delegate_task("say hello")

    assert result["status"] == "success"
    assert result["result"] == "worker complete"
    assert result["error"] == ""
