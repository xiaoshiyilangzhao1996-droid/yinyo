# memory_tool.py — 持久记忆工具 v1.0
# 对标 Hermes memory tool：add / replace / remove，target 分离 user 和 memory
import os, re

USER_CHAR_LIMIT = 1500   # ~500 tokens
MEMORY_CHAR_LIMIT = 2200  # ~800 tokens
SECTION_SEP = "\n§\n"     # 条目分隔符（对标 Hermes § 分隔符）


def _read_file(path: str) -> str:
    """读文件，不存在返回空字符串。"""
    if not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write_file(path: str, content: str):
    """写文件，自动创建目录。"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _split_entries(content: str) -> list[str]:
    """按 § 分隔符拆分记忆条目。"""
    if not content:
        return []
    # 跳过空行和纯分隔符
    entries = content.split(SECTION_SEP)
    return [e.strip() for e in entries if e.strip() and e.strip() != "§"]


def _join_entries(entries: list[str]) -> str:
    """合并条目为文件内容。"""
    return SECTION_SEP.join(e.strip() for e in entries if e.strip())


def _count_chars(entries: list[str]) -> int:
    """计算条目总字符数（不含分隔符）。"""
    return sum(len(e) for e in entries)


def _enforce_limit(entries: list[str], limit: int) -> list[str]:
    """超出限制时合并最短的条目，直到符合限制。超限单条目截断。"""
    while _count_chars(entries) > limit and len(entries) > 1:
        entries.sort(key=len)
        merged = entries[0] + "; " + entries[1]
        entries = [merged] + entries[2:]
    # 兜底：合并后仍只有 1 条且超限 → 截断
    if len(entries) == 1 and len(entries[0]) > limit:
        entries[0] = entries[0][:limit - 3] + "..."
    return entries


def memory_add(target: str, content: str, workspace: str) -> dict:
    """添加记忆条目。

    Args:
        target: "user" 或 "memory"
        content: 要添加的内容
        workspace: Agent workspace 根目录

    Returns:
        {"status": "added", "target": "user", "chars_used": 150, "chars_limit": 1500}
    """
    filename = "USER.md" if target == "user" else "MEMORY.md"
    char_limit = USER_CHAR_LIMIT if target == "user" else MEMORY_CHAR_LIMIT
    path = os.path.join(workspace, filename)

    existing = _read_file(path)
    entries = _split_entries(existing)

    # 去重检测（前 80 字符相似）
    content_head = content[:80].strip().lower()
    for e in entries:
        if e[:80].strip().lower() == content_head:
            return {"status": "duplicate", "message": "Similar entry already exists",
                    "existing": e[:100]}

    entries.append(content)
    entries = _enforce_limit(entries, char_limit)

    _write_file(path, _join_entries(entries))
    return {
        "status": "added",
        "target": target,
        "file": filename,
        "chars_used": _count_chars(entries),
        "chars_limit": char_limit,
        "entries_count": len(entries),
    }


def memory_replace(target: str, old_text: str, content: str, workspace: str) -> dict:
    """替换记忆条目（子串匹配，对标 Hermes）。

    Args:
        target: "user" 或 "memory"
        old_text: 用于匹配旧条目的唯一子串
        content: 新内容
        workspace: Agent workspace 根目录
    """
    filename = "USER.md" if target == "user" else "MEMORY.md"
    path = os.path.join(workspace, filename)

    existing = _read_file(path)
    entries = _split_entries(existing)

    # 子串匹配
    old_lower = old_text.strip().lower()
    matches = [i for i, e in enumerate(entries) if old_lower in e.lower()]

    if len(matches) == 0:
        return {"status": "not_found",
                "message": f"No entry matching '{old_text[:60]}' found"}

    if len(matches) > 1:
        previews = [entries[i][:80] for i in matches]
        return {"status": "ambiguous",
                "message": f"Found {len(matches)} matching entries",
                "matches": previews}

    entries[matches[0]] = content
    _write_file(path, _join_entries(entries))
    return {
        "status": "replaced",
        "target": target,
        "chars_used": _count_chars(entries),
    }


def memory_remove(target: str, old_text: str, workspace: str) -> dict:
    """删除记忆条目（子串匹配）。

    Args:
        target: "user" 或 "memory"
        old_text: 用于匹配旧条目的唯一子串
        workspace: Agent workspace 根目录
    """
    filename = "USER.md" if target == "user" else "MEMORY.md"
    path = os.path.join(workspace, filename)

    existing = _read_file(path)
    entries = _split_entries(existing)

    old_lower = old_text.strip().lower()
    matches = [i for i, e in enumerate(entries) if old_lower in e.lower()]

    if len(matches) == 0:
        return {"status": "not_found"}

    if len(matches) > 1:
        return {"status": "ambiguous",
                "message": f"Found {len(matches)} matching entries. Please be more specific."}

    removed = entries.pop(matches[0])
    _write_file(path, _join_entries(entries))
    return {
        "status": "removed",
        "target": target,
        "removed_preview": removed[:100],
    }


def load_memory_context(workspace: str) -> dict:
    """加载 USER.md 和 MEMORY.md 内容用于注入 system prompt。

    Returns:
        {"user": "content...", "memory": "content...",
         "user_chars": 150, "user_limit": 1500, ...}
    """
    result = {}
    for target, filename, limit in [
        ("user", "USER.md", USER_CHAR_LIMIT),
        ("memory", "MEMORY.md", MEMORY_CHAR_LIMIT),
    ]:
        path = os.path.join(workspace, filename)
        content = _read_file(path)
        entries = _split_entries(content)
        result[target] = content
        result[f"{target}_chars"] = _count_chars(entries)
        result[f"{target}_limit"] = limit
        result[f"{target}_entries"] = len(entries)
    return result


def ensure_memory_files(workspace: str):
    """确保 USER.md 和 MEMORY.md 存在，不存在则创建空文件。"""
    for filename, header in [
        ("USER.md", "# USER.md — About the user\n"),
        ("MEMORY.md", "# MEMORY.md — Agent's persistent notes\n"),
    ]:
        path = os.path.join(workspace, filename)
        if not os.path.isfile(path):
            _write_file(path, header)
