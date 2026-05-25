# vision_adapter.py — 外部视觉模型适配器 v8.0
"""将图片转换为文本描述，注入 DeepSeek Agent 上下文。

设计原则：DeepSeek V4 无原生 Vision API，用 adapter 模式桥接外部视觉模型。
支持 OpenAI GPT-4o-mini Vision（默认）和 Qwen-VL-Max（可配置）。
"""

import os, base64, json

try:
    import requests
except ImportError:
    requests = None


class VisionAdapter:
    """视觉模型适配器。将图片转为文本描述。"""

    def __init__(self, provider: str = None, api_key: str = None):
        self.provider = provider or os.environ.get("VISION_PROVIDER", "openai")
        self.api_key = api_key or os.environ.get("VISION_API_KEY", os.environ.get("OPENAI_API_KEY", ""))

        self.providers = {
            "openai": {
                "url": "https://api.openai.com/v1/chat/completions",
                "model": "gpt-4o-mini",
                "max_tokens": 300,
            },
            "qwen": {
                "url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                "model": "qwen-vl-max",
                "max_tokens": 300,
            },
        }

    def describe(self, image_source: str, query: str = "请详细描述这张图片的内容") -> dict:
        """分析图片并返回文本描述。

        Args:
            image_source: 本地路径、URL 或 base64 字符串
            query: 对图片的具体问题

        Returns:
            {"description": "...", "model": "...", "tokens": N, "error": None}
        """
        if not self.api_key or not requests:
            return {"description": "", "model": "none", "tokens": 0,
                    "error": "Vision API not configured (no VISION_API_KEY)"}

        cfg = self.providers.get(self.provider, self.providers["openai"])

        # 构建图片 content
        image_content = self._build_image_content(image_source)
        if not image_content:
            return {"description": "", "model": cfg["model"], "tokens": 0,
                    "error": f"Cannot load image: {image_source[:50]}"}

        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": query},
                image_content,
            ]
        }]

        try:
            resp = requests.post(
                cfg["url"],
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": cfg["model"],
                    "messages": messages,
                    "max_tokens": cfg["max_tokens"],
                },
                timeout=30,
            )
            data = resp.json()

            if resp.status_code != 200:
                return {"description": "", "model": cfg["model"], "tokens": 0,
                        "error": data.get("error", {}).get("message", f"HTTP {resp.status_code}")}

            description = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            return {
                "description": description,
                "model": cfg["model"],
                "tokens": usage.get("total_tokens", 0),
                "error": None,
            }
        except Exception as e:
            return {"description": "", "model": cfg["model"], "tokens": 0, "error": str(e)}

    def _build_image_content(self, source: str) -> dict | None:
        """构建 OpenAI Vision API 的 image_url content。"""
        # URL
        if source.startswith(("http://", "https://")):
            return {"type": "image_url", "image_url": {"url": source}}

        # Base64
        if source.startswith("data:image"):
            return {"type": "image_url", "image_url": {"url": source}}

        # 本地文件
        if os.path.isfile(source):
            try:
                with open(source, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                ext = os.path.splitext(source)[1].lower().lstrip(".")
                mime = f"image/{ext}" if ext in ("png", "jpeg", "jpg", "gif", "webp") else "image/png"
                return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
            except Exception:
                return None

        return None


# 全局单例
_vision_adapter: VisionAdapter | None = None


def get_vision_adapter() -> VisionAdapter:
    global _vision_adapter
    if _vision_adapter is None:
        _vision_adapter = VisionAdapter()
    return _vision_adapter
