# test_governance.py — 安全策略测试（RiskPolicy + Secret Scanner）
"""测试 governance 模块的各个功能：gate、密钥扫描、脱敏。"""

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

    def test_redact_secrets(self):
        """脱敏应将密钥替换为 [REDACTED]。"""
        text = "password=qwerty12345678 and token=ghp_abcdefg"
        result = redact_secrets(text)
        assert "[REDACTED]" in result
        assert "qwerty12345678" not in result
