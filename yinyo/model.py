# model.py — Model Gateway v3.0（DeepSeek 原生优化 + tools 参数 + Context Caching）
import os, json, time
from enum import Enum

try:
    import requests
except ImportError:
    requests = None

class ThinkingMode(Enum):
    NON_THINK = "non-think"
    THINK_HIGH = "think-high"
    THINK_MAX = "think-max"

class ModelGateway:
    """DeepSeek-first model gateway。OpenAI 兼容 API + tools 参数支持。"""
    def __init__(self, api_key: str = None, base_url: str = "https://api.deepseek.com",
                 default_model: str = "deepseek-v4-flash", thinking: ThinkingMode = ThinkingMode.NON_THINK):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.thinking = thinking
        self._cache_hits = 0
        self._cache_misses = 0

    def chat(self, messages: list, tools: list = None, thinking: ThinkingMode = None,
             max_tokens: int = 4096, temperature: float = None) -> dict:
        """★ v3.0: 标准 OpenAI tool-calling chat completion。
        
        Args:
            messages: 对话历史
            tools: OpenAI 格式工具 schema 列表（★ v2.1 缺失）
            thinking: Thinking 模式
            max_tokens: 最大输出 token
            temperature: 采样温度（NON_THINK 模式可用）
        
        Returns:
            {"content": "...", "tool_calls": [...], "finish_reason": "stop", ...}
        """
        model = self.default_model
        thinking = thinking or self.thinking

        # Mock mode
        if not self.api_key or not requests:
            return self._mock_response(messages, model, tools)

        # Primary call
        result = self._call_api(messages, tools, model, thinking, max_tokens, temperature)

        # Fallback: V4-Flash 失败 → V4-Pro
        if "error" in result and model in (None, self.default_model, "deepseek-v4-flash"):
            fallback = self._call_api(messages, tools, "deepseek-v4-pro",
                                      ThinkingMode.THINK_HIGH, max_tokens, None)
            if "error" not in fallback:
                fallback["_fallback"] = True
                return fallback

        return result

    def chat_with_retry(self, messages: list, tools: list = None, thinking: ThinkingMode = None,
                        max_tokens: int = 4096, max_retries: int = 2) -> dict:
        """带重试的 chat（最多 2 次，指数退避）。"""
        last_error = None
        for attempt in range(max_retries + 1):
            result = self.chat(messages, tools, thinking, max_tokens)
            if "error" not in result:
                return result
            last_error = result["error"]
            if attempt < max_retries:
                time.sleep(2 ** attempt)
        return {"error": f"All {max_retries+1} attempts failed: {last_error}"}

    def _call_api(self, messages: list, tools: list, model: str,
                  thinking: ThinkingMode, max_tokens: int, temperature: float) -> dict:
        """实际的 API 调用。"""
        url = f"{self.base_url}/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}",
                   "Content-Type": "application/json"}

        payload = {"model": model, "messages": messages, "max_tokens": max_tokens}

        # ★ 发送 tools schema + 并行调用
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
            payload["parallel_tool_calls"] = True  # v4.0: DeepSeek 原生并行

        # Thinking 模式
        if thinking != ThinkingMode.NON_THINK:
            thinking_type = "high" if thinking == ThinkingMode.THINK_HIGH else "max"
            payload["thinking"] = {"type": thinking_type}
        elif temperature is not None:
            payload["temperature"] = temperature

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=120)
            data = resp.json()

            if resp.status_code != 200:
                return {"error": data.get("error", {}).get("message", f"HTTP {resp.status_code}")}

            # Context Caching 识别
            if "x-ds-cache-hit" in resp.headers:
                self._cache_hits += 1
            else:
                self._cache_misses += 1

            choice = data["choices"][0]
            msg = choice.get("message", {})

            result = {
                "content": msg.get("content", ""),
                "model": data.get("model", model),
                "usage": data.get("usage", {}),
                "finish_reason": choice.get("finish_reason", ""),
            }

            # reasoning_content 回传
            if "reasoning_content" in msg:
                result["reasoning_content"] = msg["reasoning_content"]

            # ★ 解析 tool_calls
            if "tool_calls" in msg:
                result["tool_calls"] = msg["tool_calls"]

            return result

        except Exception as e:
            return {"error": str(e)}

    def _mock_response(self, messages: list, model: str, tools: list = None) -> dict:
        """Mock 模式：返回假响应。如果有 tools，mock 一个 read 调用。"""
        last = messages[-1]["content"] if messages else ""
        tool_names = [t["function"]["name"] for t in tools] if tools else []
        if "do_read" in tool_names and "read" in last.lower():
            return {
                "content": "",
                "model": model + "-mock",
                "usage": {"prompt_tokens": 100, "completion_tokens": 10},
                "finish_reason": "tool_calls",
                "tool_calls": [{
                    "id": "call_mock_001",
                    "type": "function",
                    "function": {"name": "do_read", "arguments": '{"path": "test.txt", "limit": 10}'}
                }]
            }
        return {
            "content": f"Mock response: task completed.",
            "model": model + "-mock",
            "usage": {"prompt_tokens": 100, "completion_tokens": 10},
            "finish_reason": "stop",
        }

    @property
    def cache_stats(self) -> dict:
        return {"hits": self._cache_hits, "misses": self._cache_misses}
