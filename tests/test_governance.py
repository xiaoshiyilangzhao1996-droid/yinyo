# test_governance.py — 安全策略测试（RiskPolicy + Secret Scanner）
"""测试 governance 模块的各个功能：gate、密钥扫描、脱敏。"""

import json
import pytest, os, tempfile
from governance import RiskPolicy, scan_secrets, redact_secrets


class TestRiskPolicy:
    """RiskPolicy 风险策略测试。"""

    def test_block_always(self):
        """BLOCK_ALWAYS 策略应拦截。"""
        policy = RiskPolicy(workspace=".")
        result = policy.gate("delete remote resources")
        assert result.action == "blocked"
        assert "blocked" in result.reason

    def test_confirm_required(self):
        """CONFIRM_REQUIRED 策略应提示确认。"""
        policy = RiskPolicy(workspace=".")
        result = policy.gate("write files outside workspace")
        assert result.action == "confirm"

    def test_default_allow(self):
        """未在策略列表中的动作应放行。"""
        policy = RiskPolicy(workspace=".")
        result = policy.gate("read a file")
        assert result.action == "allow"

    def test_gate_for_tool_write_outside_workspace(self):
        """do_write 写入 workspace 外应被拦截。"""
        policy = RiskPolicy(workspace="/safe/dir")
        result = policy.gate_for_tool("do_write", {"path": "/outside/file.txt"})
        assert result.action == "blocked"
        assert "outside workspace" in result.reason

    def test_gate_for_tool_write_inside_workspace(self):
        """do_write 写入 workspace 内应放行。"""
        policy = RiskPolicy(workspace="/safe/dir")
        result = policy.gate_for_tool("do_write", {"path": "/safe/dir/file.txt"})
        assert result.action == "allow"

    def test_gate_for_tool_dangerous_command(self):
        """do_run 危险命令应被拦截。"""
        policy = RiskPolicy(workspace=".")
        result = policy.gate_for_tool("do_run", {"command": "rm -rf /"})
        assert result.action == "blocked"
        assert "Dangerous command" in result.reason

    def test_gate_for_tool_safe_command(self):
        """do_run 安全命令应放行。"""
        policy = RiskPolicy(workspace=".")
        result = policy.gate_for_tool("do_run", {"command": "ls -la"})
        assert result.action == "allow"

    def test_in_workspace_edge_cases(self):
        """_in_workspace 边界条件。"""
        policy = RiskPolicy(workspace="/workspace")
        # 恰好 workspace
        assert policy._in_workspace("/workspace/file.txt")
        # 不在 workspace
        assert not policy._in_workspace("/etc/passwd")
        # workspace 自身
        assert policy._in_workspace("/workspace")

    def test_confirm_tool_rejects_legacy_boolean(self, tmp_path):
        """CONFIRM 工具不能靠裸 _confirmed 布尔值绕过审计。"""
        from evidence import EvidenceLedger
        from tools import registry, set_tool_workspace, execute_tool_with_evidence

        set_tool_workspace(str(tmp_path))
        ledger = EvidenceLedger(str(tmp_path / "runs" / "run-001"))
        result = execute_tool_with_evidence(
            registry,
            "do_write",
            {"path": "out.txt", "content": "blocked", "_confirmed": True},
            ledger,
            RiskPolicy(workspace=str(tmp_path)),
            "run-001",
            1,
        )

        assert result["_blocked"] is True
        assert "structured confirmation metadata" in result["error"]
        assert not (tmp_path / "out.txt").exists()

    def test_confirm_tool_records_structured_metadata(self, tmp_path):
        """CONFIRM 工具的确认元数据应写入 evidence。"""
        from evidence import EvidenceLedger
        from tools import registry, set_tool_workspace, execute_tool_with_evidence

        set_tool_workspace(str(tmp_path))
        ledger = EvidenceLedger(str(tmp_path / "runs" / "run-001"))
        confirmation = {
            "actor": "test-operator",
            "scope": "do_write",
            "reason": "governance evidence test",
            "expires_at": "2099-01-01T00:00:00Z",
        }
        result = execute_tool_with_evidence(
            registry,
            "do_write",
            {"path": "out.txt", "content": "ok", "confirmation": confirmation},
            ledger,
            RiskPolicy(workspace=str(tmp_path)),
            "run-001",
            1,
        )

        assert result["wrote"] == 2
        record = json.loads((tmp_path / "runs" / "run-001" / "evidence.jsonl").read_text(encoding="utf-8").splitlines()[0])
        assert record["args"]["confirmation"]["actor"] == "test-operator"
        assert record["args"]["confirmation"]["scope"] == "do_write"
        assert record["result"]["preview"].find("_confirmation") >= 0


class TestSecretScanner:
    """密钥扫描和脱敏测试。"""

    def test_scan_quoted(self):
        """引号包围的密钥应被检测。"""
        found = scan_secrets("password='qwerty12345678'")
        assert len(found) >= 1

    def test_scan_unquoted(self):
        """BU-03: 无引号密钥应被检测。"""
        found = scan_secrets("password=qwerty12345678")
        assert len(found) >= 1

    def test_scan_github_token(self):
        """GitHub token 格式应被检测。"""
        found = scan_secrets("export GITHUB_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz123456")
        assert len(found) >= 1

    def test_scan_openai_key(self):
        """OpenAI API key 格式应被检测。"""
        found = scan_secrets("OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz123456")
        assert len(found) >= 1

    def test_scan_bearer_token(self):
        """Bearer token 应被检测。"""
        found = scan_secrets("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abcdefghijklmnop")
        assert len(found) >= 1

    def test_scan_no_secret(self):
        """无密钥文本不应误报。"""
        found = scan_secrets("hello world, this is normal text")
        assert len(found) == 0

    def test_scan_short_value_no_false_positive(self):
        """短值（如 KEY=abc）不应误报。"""
        found = scan_secrets("KEY=abc")
        assert len(found) == 0

    def test_scan_empty_template_values_do_not_cross_lines(self):
        text = "app_secret=\nverify_token=\ndeepseek_api_key=\ndeepseek_base_url=https://api.deepseek.com\n"
        found = scan_secrets(text)
        assert found == []

    def test_scan_json_secret_key_value(self):
        found = scan_secrets('{"api_key":"abcd1234abcd1234"}')
        assert len(found) >= 1

    def test_redact_secrets(self):
        """脱敏应将密钥替换为 [REDACTED]。"""
        text = "password=qwerty12345678 and token=ghp_abcdefg"
        result = redact_secrets(text)
        assert "[REDACTED]" in result
        assert "qwerty12345678" not in result
