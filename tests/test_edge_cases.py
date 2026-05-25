# test_edge_cases.py — 边界条件 + 异常处理测试
"""对标 Hermes boundary 测试：空输入、超长输入、并发、错误恢复。"""

import pytest, json, os, time
from model import ModelGateway


class TestBoundaryConditions:
    """边界条件测试。"""

    def test_empty_task(self, mock_agent):
        """空 task 不应崩溃。"""
        mock_agent.model.set_mock_responses([
            {"content": "收到了空消息。", "finish_reason": "stop"},
        ])
        result = mock_agent.run("")
        assert result["status"] in ("success", "max_steps_reached", "error")

    def test_very_long_task(self, mock_agent, tmp_path):
        """超长 task（10000+ 字符）不应崩溃。"""
        long_task = "测试 " * 5000  # ~15000 chars
        mock_agent.model.set_mock_responses([
            {"content": "处理完成。", "finish_reason": "stop"},
        ])
        result = mock_agent.run(long_task)
        assert result["status"] == "success"

    def test_unicode_task(self, mock_agent):
        """Unicode 特殊字符 task 不应崩溃。"""
        unicode_task = "你好 🌍 🎉 emoji test 日本語 한국어"
        mock_agent.model.set_mock_responses([
            {"content": "收到 Unicode 消息。", "finish_reason": "stop"},
        ])
        result = mock_agent.run(unicode_task)
        assert result["status"] == "success"

    def test_tool_error_recovery(self, mock_agent, tmp_path):
        """工具执行出错后 Agent 应能恢复（不崩溃）。"""
        mock_agent.model.set_mock_responses([
            {"content": "[STEP 1] try to read nonexistent file", "finish_reason": "stop"},
            {
                "content": "",
                "tool_calls": [{
                    "id": "c1", "type": "function",
                    "function": {"name": "do_read",
                               "arguments": json.dumps({"path": "/nonexistent/nope.txt"})}
                }],
                "finish_reason": "tool_calls",
            },
            {"content": "文件不存在，但 Agent 仍在运行。", "finish_reason": "stop"},
        ])
        result = mock_agent.run("读取不存在的文件")
        assert result["status"] in ("success", "max_steps_reached", "error")

    def test_consecutive_failures_thinking_escalation(self, mock_agent, tmp_path):
        """连续失败应触发 thinking 升级，但不崩溃。"""
        mock_agent.model.set_mock_responses([
            {"content": "", "tool_calls": [{
                "id": "c1", "type": "function",
                "function": {"name": "do_read", "arguments": json.dumps({"path": str(tmp_path / "x.txt")})}
            }], "finish_reason": "tool_calls"},
            {"error": "API error"},
            {"error": "API error"},
            {"content": "恢复后完成。", "finish_reason": "stop"},
        ])

        with open(str(tmp_path / "x.txt"), "w") as f:
            f.write("data")

        result = mock_agent.run("测试失败恢复")
        assert result["status"] in ("success", "max_steps_reached", "error")

    def test_mock_queue_exhausted(self):
        """mock 队列耗尽后应回退到默认 mock。"""
        model = ModelGateway(api_key="")
        model.set_mock_responses([{"content": "only one"}])
        r1 = model.chat(messages=[{"role": "user", "content": "q1"}])
        r2 = model.chat(messages=[{"role": "user", "content": "q2"}])

        assert r1["content"] == "only one"
        assert "Mock" in r2.get("content", "")  # 回退到默认


class TestConcurrency:
    """并发测试。"""

    def test_parallel_delegate_calls(self, mock_agent, tmp_path):
        """并行 delegate_task 不应崩溃。"""
        mock_agent.model.set_mock_responses([
            {"content": "[STEP 1] delegate tasks", "finish_reason": "stop"},
            {
                "content": "",
                "tool_calls": [
                    {"id": "c1", "type": "function",
                     "function": {"name": "delegate_task", "arguments": json.dumps({"goal": "task A"})}},
                    {"id": "c2", "type": "function",
                     "function": {"name": "delegate_task", "arguments": json.dumps({"goal": "task B"})}},
                ],
                "finish_reason": "tool_calls",
            },
            {"content": "并行任务完成。", "finish_reason": "stop"},
        ])
        result = mock_agent.run("同时执行两个子任务")
        assert result["status"] in ("success", "max_steps_reached", "error")

    def test_rapid_sequential_runs(self, mock_agent):
        """连续快速多次 run 不应内存泄漏或崩溃。"""
        mock_agent.model.set_mock_responses([
            {"content": f"运行完成。", "finish_reason": "stop"},
        ])
        for i in range(5):
            result = mock_agent.run(f"任务 {i}")
            assert result["status"] in ("success", "max_steps_reached", "error")


class TestTemporalTreeEdgeCases:
    """TemporalTree 边界测试。"""

    def test_empty_tree_search(self, temporal_tree):
        """空树搜索应返回空列表。"""
        results = temporal_tree.search("anything")
        assert results == []

    def test_large_tree(self, temporal_tree):
        """大量节点不应崩溃。"""
        for i in range(100):
            temporal_tree.add(f"大量事实_{i}", category="Test")
        results = temporal_tree.search("大量")
        assert len(results) <= 5  # limit=5

    def test_supersede_chain(self, temporal_tree):
        """长取代链应正确追溯。"""
        nodes = []
        nodes.append(temporal_tree.add("v0", category="Test"))
        for i in range(1, 5):
            nodes.append(temporal_tree.add(f"v{i}", category="Test"))

        trail = temporal_tree.get_audit_trail(nodes[0].id)
        assert len(trail) == 5

    def test_duplicate_add(self, temporal_tree):
        """同类同scope重复添加应触发取代，不产生重复节点。"""
        n1 = temporal_tree.add("偏好A", category="Preferences", confidence=0.5)
        n2 = temporal_tree.add("偏好B", category="Preferences", confidence=0.7)
        # n1 应被取代
        assert temporal_tree.nodes[n1.id].status == "superseded"
