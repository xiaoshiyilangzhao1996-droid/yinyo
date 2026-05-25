# feishu_card.py — 飞书 Card 2.0 消息构建器 v1.0
# 对标 Hermes feishu.py _build_markdown_card_payload() + OpenClaw deliver.ts
import json
from feishu_format import optimize, split_long_message, strip_markdown_to_plain

# Feishu Card 2.0 错误码
CARD_INVALID_ERROR = 230099


def build_card_payload(markdown: str, title: str = "") -> str:
    """构建 Feishu Card 2.0 消息 payload。

    Args:
        markdown: 已优化过的 Markdown 文本
        title: 卡片标题（空则用默认）

    Returns:
        JSON 字符串，可直接作为 msg_type='interactive' 的 content
    """
    optimized = optimize(markdown)

    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {
                "tag": "plain_text",
                "content": title or "YINYO"
            },
            "template": "wathet" if title else "blue"
        },
        "elements": [
            {"tag": "markdown", "content": optimized}
        ]
    }

    # 如果内容超长，添加 footer 提示
    if len(optimized) > 8000:
        card["elements"].append({
            "tag": "note",
            "elements": [{"tag": "plain_text", "content": "📄 内容较长，已分段显示"}]
        })

    return json.dumps(card, ensure_ascii=False)


def build_text_payload(text: str) -> str:
    """构建纯文本消息 payload（Card 拒绝时降级）。"""
    plain = strip_markdown_to_plain(text)
    return json.dumps({"text": plain}, ensure_ascii=False)


def build_card_messages(markdown: str, title: str = "") -> list[dict]:
    """构建一个或多个 Card 2.0 消息（自动分段）。

    Returns:
        [{"msg_type": "interactive", "content": "..."}, ...]
    """
    chunks = split_long_message(markdown)
    messages = []
    for i, chunk in enumerate(chunks):
        chunk_title = title if i == 0 else f"{title} ({i+1}/{len(chunks)})" if title else ""
        messages.append({
            "msg_type": "interactive",
            "content": build_card_payload(chunk, chunk_title)
        })
    return messages


def is_card_invalid_error(error_msg: str) -> bool:
    """检测是否为 Card 内容格式错误。"""
    if not error_msg:
        return False
    return (
        str(CARD_INVALID_ERROR) in str(error_msg) or
        "Failed to create card content" in str(error_msg) or
        "content format of the post type is incorrect" in str(error_msg)
    )
