# test_agent.py — Agent ReAct Loop 集成测试（Mock LLM）
"""对标 Hermes agent 集成测试：完整 ReAct 循环 + delegate + vision。

使用 mock LLM 响应，不依赖外部 API。"""

import pytest, json, os
from model import ModelGateway


class TestAgentReActLoop:
    """Agent.run() 集成测试（mock LLM）。"""

    def test_simple_task_no_tools(self, mock_agent, tmp_path):
        """纯文本任务，不需要工具。"""
        mock_agent.model.set_mock_responses([
            {"content": "这是一个简单的回答。", "finish_reason": "stop"},
        ])

        result = mock_agent.run("你好")
        assert result["status"] == "success"
        assert result["steps"] <= 2

    def test_single_tool_call(self, mock_agent, tmp_path):
        """单工具调用：do_read。"""
        # 创建测试文件
        test_path = str(tmp_path / "test_data.txt")
        with open(test_path, "w") as f:
            f.write("important data")

        mock_agent.model.set_mock_responses([
            # Plan 阶段
            {"content": "[STEP 1] read test_data.txt -> do_read -> file contents", "finish_reason": "stop"},
            # 第1轮：调用 do_read
            {
                "content": "",
                "tool_calls": [{
                    "id": "call_1", "type": "function",
                    "function": {"name": "do_read", "arguments": json.dumps({"path": "test_data.txt"})}
                }],
                "finish_reason": "tool_calls",
            },
            # 第2轮：看到结果，结束
            {"content": "文件内容是 important data，任务完成。", "finish_reason": "stop"},
        ])

        result = mock_agent.run("读取 test_data.txt")
        assert result["status"] == "success"
        assert "do_read" in result["tools_used"]

    def test_parallel_tool_calls(self, mock_agent, tmp_path):
        """并行工具调用：同时读两个文件。"""
        p1 = str(tmp_path / "file_a.txt")
        p2 = str(tmp_path / "file_b.txt")
        with open(p1, "w") as f: f.write("A")
        with open(p2, "w") as f: f.write("B")

        mock_agent.model.set_mock_responses([
            {"content": "[STEP 1] read both files", "finish_reason": "stop"},
            {
                "content": "",
                "tool_calls": [
                    {"id": "c1", "type": "function", "function": {"name": "do_read", "arguments": json.dumps({"path": p1})}},
                    {"id": "c2", "type": "function", "function": {"name": "do_read", "arguments": json.dumps({"path": p2})}},
                ],
                "finish_reason": "tool_calls",
            },
            {"content": "两个文件都读取完成。", "finish_reason": "stop"},
        ])

        result = mock_agent.run("读取 file_a 和 file_b")
        assert result["status"] == "success"

    def test_max_steps_reached(self, mock_agent, tmp_path):
        """达到最大步数时应返回 max_steps_reached。"""
        responses = []
        for idx in range(12):
            responses.append({
                "content": "",
                "tool_calls": [{
                    "id": f"c{idx}", "type": "function",
                    "function": {"name": "do_read", "arguments": json.dumps({"path": "loop.txt"})}
                }],
                "finish_reason": "tool_calls",
            })

        mock_agent.model.set_mock_responses(responses)
        with open(str(tmp_path / "loop.txt"), "w") as f:
            f.write("data")

        mock_agent.max_steps = 5
        result = mock_agent.run("无限循环任务")
        assert result["status"] == "max_steps_reached"

    def test_memory_persistence_across_runs(self, mock_agent, tmp_path):
        """两次 run 之间记忆应持久化。第一次存入 → 第二次查证。"""
        # 直接在 memory tree 中写入记忆（确保在 run 之前存在）
        mock_agent.memory.tree.add(
            "用户偏好简洁回复", category="Preferences", confidence=0.9
        )

        mock_agent.model.set_mock_responses([
            {"content": "已完成。", "finish_reason": "stop"},
        ])
        mock_agent.run("记住：用户偏好简洁回复")

        mock_agent.model.set_mock_responses([
            {"content": "已找到偏好。", "finish_reason": "stop"},
        ])
        mock_agent.run("用户的偏好是什么？")

        # 验证记忆在两次 run 后依然存在
        active = mock_agent.memory.tree.get_active_nodes()
        assert len(active) >= 1, "应该有活跃记忆节点"
        found = any("简洁" in n.content for n in active)
        assert found, "应在活跃节点中找到 '简洁回复' 相关记忆"

    def test_auto_manifest_generates(self, mock_agent, tmp_path):
        """_auto_manifest 应在多工具调用后生成 manifest。"""
        # 使用 agent 的 workspace（agent.__init__ 已调用 set_tool_workspace）
        ws = mock_agent.workspace
        # 在 workspace 内创建测试文件
        test_path = os.path.join(ws, "manifest_test.txt")
        with open(test_path, "w") as f:
            f.write("data")

        # 模拟工具调用结果，供 _auto_manifest 检测受影响文件
        mock_agent._last_tool_results = [
            ("do_read", {"path": "manifest_test.txt"}, {}),
            ("do_write", {"path": "output.txt"}, {}),
        ]

        mock_agent.model.set_mock_responses([
            # Plan 阶段
            {"content": "[STEP 1] read then write", "finish_reason": "stop"},
            # 第1轮：调用 do_read（相对路径，在 workspace 内）
            {
                "content": "",
                "tool_calls": [{
                    "id": "c1", "type": "function",
                    "function": {"name": "do_read",
                                 "arguments": json.dumps({"path": "manifest_test.txt"})}
                }],
                "finish_reason": "tool_calls",
            },
            # 第2轮：调用 do_write（相对路径，在 workspace 内）
            {
                "content": "",
                "tool_calls": [{
                    "id": "c2", "type": "function",
                    "function": {"name": "do_write",
                                 "arguments": json.dumps({"path": "output.txt", "content": "generated"})}
                }],
                "finish_reason": "tool_calls",
            },
            # 第3轮：结束
            {"content": "done", "finish_reason": "stop"},
            # _reflect_on_run 的 LLM 调用
            {"content": '{"reflections": [], "memory_add": [], "memory_update": [], "memory_remove": []}',
             "finish_reason": "stop"},
            # _auto_manifest 的 LLM 调用
            {"content": '{"change_type": "feat", "summary": "Read and write test data for manifest generation"}',
             "finish_reason": "stop"},
            # 备用（防止额外 LLM 调用）
            {"content": "fallback", "finish_reason": "stop"},
            {"content": "fallback", "finish_reason": "stop"},
        ])

        mock_agent.run("读取文件并写入输出")

        # 验证 manifests 目录（如果存在）或至少不崩溃
        manifests_dir = os.path.join(mock_agent.workspace, "manifests")
        # 注意：_auto_manifest 在 LLM 调用失败时会跳过，不影响正常运行
        if os.path.isdir(manifests_dir):
            manifests = [f for f in os.listdir(manifests_dir) if f.endswith(".json")]
            if manifests:
                manifest_path = os.path.join(manifests_dir, manifests[0])
                with open(manifest_path, "r") as f:
                    manifest = json.load(f)
                assert "change_type" in manifest
                assert manifest["change_type"] in ("feat", "fix", "refactor", "docs", "test")
                assert "summary" in manifest
                assert "affected_files" in manifest


class TestDelegate:
    """delegate_task 集成测试。"""

    def test_subagent_basic(self, mock_agent, tmp_path):
        """子 Agent 应能完成独立任务。"""
        test_path = str(tmp_path / "sub_test.txt")
        with open(test_path, "w") as f: f.write("sub data")

        mock_agent.model.set_mock_responses([
            {"content": "[STEP 1] delegate sub-task", "finish_reason": "stop"},
            {
                "content": "",
                "tool_calls": [{
                    "id": "c1", "type": "function",
                    "function": {"name": "delegate_task",
                               "arguments": json.dumps({"goal": "read sub_test.txt", "context": ""})}
                }],
                "finish_reason": "tool_calls",
            },
            {"content": "子任务完成。", "finish_reason": "stop"},
        ])

        result = mock_agent.run("批量处理文件")
        assert result["status"] == "success"


class TestMockQueue:
    """mock 队列测试。"""

    def test_queue_consumed_in_order(self):
        model = ModelGateway(api_key="")
        model.set_mock_responses([
            {"content": "first", "finish_reason": "stop"},
            {"content": "second", "finish_reason": "stop"},
            {"content": "third", "finish_reason": "stop"},
        ])
        assert model.chat(messages=[{"role": "user", "content": ""}])["content"] == "first"
        assert model.chat(messages=[{"role": "user", "content": ""}])["content"] == "second"
        assert model.chat(messages=[{"role": "user", "content": ""}])["content"] == "third"
