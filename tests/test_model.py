# test_model.py — Model Gateway + Provider Chain 单元测试
"""对标 Hermes model 测试：fallback、mock、thinking modes。"""

import pytest
from model import ModelGateway, ThinkingMode


class TestModelGateway:
    """ModelGateway 核心功能测试。"""

    def test_mock_mode_no_api_key(self):
        """无 API key 时应进入 mock 模式，不抛异常。"""
        model = ModelGateway(api_key="")
        result = model.chat(messages=[{"role": "user", "content": "hello"}])
        assert "error" not in result
        assert "Mock" in result.get("content", "")

    def test_programmable_mock(self):
        """set_mock_responses 应依次返回预设响应。"""
        model = ModelGateway(api_key="")
        model.set_mock_responses([
            {"content": "response 1", "finish_reason": "stop"},
            {"content": "response 2", "finish_reason": "stop"},
        ])

        r1 = model.chat(messages=[{"role": "user", "content": "q1"}])
        r2 = model.chat(messages=[{"role": "user", "content": "q2"}])

        assert r1["content"] == "response 1"
        assert r2["content"] == "response 2"

    def test_mock_with_tool_calls(self):
        """mock 模式应能模拟 tool_calls。"""
        model = ModelGateway(api_key="")
        model.set_mock_responses([{
            "content": "",
            "tool_calls": [{
                "id": "call_001",
                "type": "function",
                "function": {"name": "do_read", "arguments": '{"path": "test.txt"}'}
            }],
            "finish_reason": "tool_calls",
        }])

        result = model.chat(
            messages=[{"role": "user", "content": "read test.txt"}],
            tools=[{"function": {"name": "do_read"}}]
        )
        assert "tool_calls" in result
        assert result["tool_calls"][0]["function"]["name"] == "do_read"

    def test_provider_chain_built(self):
        """provider_chain 应至少包含 DeepSeek Flash 和 Pro。"""
        model = ModelGateway(api_key="sk-test")
        chain = model.provider_chain
        assert len(chain) >= 2
        models = [p["model"] for p in chain]
        assert "deepseek-v4-flash" in models
        assert "deepseek-v4-pro" in models

    def test_chat_with_retry(self):
        """chat_with_retry 在 mock 模式下应正常返回。"""
        model = ModelGateway(api_key="")
        result = model.chat_with_retry(
            messages=[{"role": "user", "content": "hello"}]
        )
        assert "error" not in result

    def test_thinking_modes(self):
        """三种 Thinking Mode 枚举应可用。"""
        assert ThinkingMode.NON_THINK.value == "non-think"
        assert ThinkingMode.THINK_HIGH.value == "think-high"
        assert ThinkingMode.THINK_MAX.value == "think-max"

    def test_clear_mock_responses(self):
        """清除 mock 队列后应回退到默认 mock。"""
        model = ModelGateway(api_key="")
        model.set_mock_responses([{"content": "custom"}])
        assert model.chat(messages=[{"role": "user", "content": "q"}])["content"] == "custom"

        model.clear_mock_responses()
        result = model.chat(messages=[{"role": "user", "content": "q"}])
        assert "Mock" in result.get("content", "")

    def test_cache_stats(self):
        """cache_stats 应返回字典。"""
        model = ModelGateway(api_key="sk-test")
        stats = model.cache_stats
        assert "hits" in stats
        assert "misses" in stats
