# model.py — Model Gateway v8.1（Provider Chain + DeepSeek 原生优化）
import os, json, time
from enum import Enum
from dataclasses import dataclass

try:
    import requests
except ImportError:
    requests = None

class ThinkingMode(Enum):
    NON_THINK = "non-think"
    THINK_HIGH = "think-high"
    THINK_MAX = "think-max"

@dataclass
class ProviderConfig:
    provider: str
    model: str
    api_key: str = ""
    base_url: str = ""
    thinking: ThinkingMode = ThinkingMode.NON_THINK


class ModelGateway:
    """DeepSeek-first model gateway with provider chain fallback."""

    def __init__(self, api_key: str = None, base_url: str = "https://api.deepseek.com",
                 default_model: str = "deepseek-v4-flash", thinking: ThinkingMode = ThinkingMode.NON_THINK):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.thinking = thinking
        self._cache_hits = 0
        self._cache_misses = 0

        # v8.0: Provider chain
        self.provider_chain = self._build_provider_chain()

    def _build_provider_chain(self) -> list:
        """构建 provider 降级链：DeepSeek Flash → Pro → GLM（如果配置）。"""
        chain = [
            {"provider": "deepseek", "model": "deepseek-v4-flash",
             "api_key": self.api_key, "base_url": self.base_url},
            {"provider": "deepseek", "model": "deepseek-v4-pro",
             "api_key": self.api_key, "base_url": self.base_url},
        ]
        # GLM fallback（如果配置了环境变量）
        glm_key = os.environ.get("GLM_API_KEY", "")
        if glm_key:
            chain.append({
                "provider": "zhipu", "model": "glm-4-flash",
                "api_key": glm_key,
                "base_url": "https://open.bigmodel.cn/api/paas/v4",
            })
        return chain

    def chat(self, messages: list, tools: list = None, thinking: ThinkingMode = None,
             max_tokens: int = 4096, temperature: float = None) -> dict:
        model = self.default_model
        thinking = thinking or self.thinking

        if not self.api_key or not requests:
            return self._mock_response(messages, model, tools)

        # v8.0: 遍历 provider chain
        for i, provider in enumerate(self.provider_chain):
            result = self._call_api(
                messages, tools, provider["model"], thinking, max_tokens, temperature,
                api_key=provider["api_key"], base_url=provider["base_url"],
            )
            if "error" not in result:
                if i > 0:
                    result["_fallback"] = True
                    result["_fallback_from"] = self.provider_chain[0]["model"]
                return result

        # 全部失败
        return {"error": "All providers in chain exhausted"}

    def chat_with_retry(self, messages: list, tools: list = None, thinking: ThinkingMode = None,
                        max_tokens: int = 4096, max_retries: int = 2) -> dict:
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
                  thinking: ThinkingMode, max_tokens: int, temperature: float,
                  api_key: str = None, base_url: str = None) -> dict:
        api_key = api_key or self.api_key
        base_url = (base_url or self.base_url).rstrip("/")
        url = f"{base_url}/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}",
                   "Content-Type": "application/json"}

        payload = {"model": model, "messages": messages, "max_tokens": max_tokens}

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
            payload["parallel_tool_calls"] = True

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

            if "reasoning_content" in msg:
                result["reasoning_content"] = msg["reasoning_content"]
            if "tool_calls" in msg:
                result["tool_calls"] = msg["tool_calls"]

            return result

        except Exception as e:
            return {"error": str(e)}

    def _mock_response(self, messages: list, model: str, tools: list = None) -> dict:
        last = messages[-1]["content"] if messages else ""
        tool_names = [t["function"]["name"] for t in tools] if tools else []

        # v8.1: Programmable mock — if _mock_queue is set, consume from it
        if hasattr(self, '_mock_queue') and self._mock_queue:
            return self._mock_queue.pop(0)

        if "do_read" in tool_names and "read" in last.lower():
            return {
                "content": "", "model": model + "-mock",
                "usage": {"prompt_tokens": 100, "completion_tokens": 10},
                "finish_reason": "tool_calls",
                "tool_calls": [{
                    "id": "call_mock_001", "type": "function",
                    "function": {"name": "do_read", "arguments": '{"path": "test.txt", "limit": 10}'}
                }]
            }
        return {
            "content": "Mock response: task completed.",
            "model": model + "-mock",
            "usage": {"prompt_tokens": 100, "completion_tokens": 10},
            "finish_reason": "stop",
        }

    def set_mock_responses(self, responses: list[dict]):
        """v8.1: 设置可编程 mock 响应队列。每次 chat() 调用依次消费。

        Args:
            responses: List of response dicts, each containing content/tool_calls/finish_reason.
                       Example: [{"content": "done", "finish_reason": "stop"}]
        """
        self._mock_queue = list(responses)

    def clear_mock_responses(self):
        """清空 mock 队列。"""
        self._mock_queue = []

    @property
    def cache_stats(self) -> dict:
        return {"hits": self._cache_hits, "misses": self._cache_misses}
