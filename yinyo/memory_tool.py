# memory_tool.py — Memory CRUD Tool v8.1
"""对标 Hermes memory tool（add/replace/remove），扩展 TemporalTree 操作。

新增 v8.0 操作：supersede（事实取代）、audit（版本追溯）、search（Multi-Scope 检索）。
"""

import os, json
from memory import MemoryStore

MEMORY_WORKSPACE: str | None = None

# 容量限制
USER_LIMIT = 1500      # USER.md 字符上限
MEMORY_LIMIT = 10000   # MEMORY.md 字符上限（v8.0 扩容到10K）


def set_memory_workspace(workspace: str):
    global MEMORY_WORKSPACE
    MEMORY_WORKSPACE = workspace


def ensure_memory_files(workspace: str):
    """确保 USER.md 和 MEMORY.md 存在。"""
    for fname, header in [
        ("USER.md", "# USER.md — About the user\n\n"),
        ("MEMORY.md", "# MEMORY.md — Agent's persistent notes\n\n"),
    ]:
        path = os.path.join(workspace, fname)
        if not os.path.isfile(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write(header)


def load_memory_context(workspace: str) -> dict:
    """加载 USER.md 和 MEMORY.md 用于 system prompt 注入。"""
    result = {"user": "", "user_chars": 0, "user_limit": USER_LIMIT,
              "memory": "", "memory_chars": 0, "memory_limit": MEMORY_LIMIT}

    for key, fname, limit in [
        ("user", "USER.md", USER_LIMIT),
        ("memory", "MEMORY.md", MEMORY_LIMIT),
    ]:
        path = os.path.join(workspace, fname)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            result[key] = content[:limit]
            result[f"{key}_chars"] = len(content)

    return result


# ── 低层级操作（供 agent 调用） ──

def _read_file(path: str) -> str:
    if not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write_file(path: str, content: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _split_entries(content: str) -> list[str]:
    """按 § 分隔符拆分条目。"""
    return [e.strip() for e in content.split("§") if e.strip()]


def _join_entries(entries: list[str]) -> str:
    return "\n§\n".join(entries)


def memory_add(target: str, content: str, workspace: str) -> dict:
    """添加记忆条目。"""
    if target not in ("user", "memory"):
        return {"ok": False, "error": f"Invalid target: {target}"}

    fname = "USER.md" if target == "user" else "MEMORY.md"
    limit = USER_LIMIT if target == "user" else MEMORY_LIMIT
    path = os.path.join(workspace, fname)

    current = _read_file(path)
    entries = _split_entries(current)

    # 去重：前 80 字符相似即判重复
    prefix = content[:80]
    for e in entries:
        if e[:80] == prefix:
            return {"ok": False, "error": "Duplicate entry (first 80 chars match)"}

    entries.append(content)

    # 容量控制：超出限制时合并最短条目
    while len(_join_entries(entries)) > limit and len(entries) > 1:
        shortest_idx = min(range(len(entries)), key=lambda i: len(entries[i]))
        if shortest_idx > 0:
            entries[shortest_idx - 1] += "; " + entries.pop(shortest_idx)
        else:
            entries[shortest_idx + 1] = entries.pop(shortest_idx) + "; " + entries[shortest_idx + 1]

    # 写入
    final = _join_entries(entries)
    if not final.startswith("#"):
        header = _read_file(path).split("§")[0].split("\n\n")[0] + "\n\n" if "\n\n" in _read_file(path) else ""
        final = header + final

    _write_file(path, final)
    return {"ok": True, "target": target, "chars": len(final), "limit": limit}


def memory_replace(target: str, old_text: str, new_text: str, workspace: str) -> dict:
    """子串匹配替换。"""
    if target not in ("user", "memory"):
        return {"ok": False, "error": f"Invalid target: {target}"}

    fname = "USER.md" if target == "user" else "MEMORY.md"
    path = os.path.join(workspace, fname)
    current = _read_file(path)

    count = current.count(old_text)
    if count == 0:
        return {"ok": False, "error": "old_text not found"}
    if count > 1:
        return {"ok": False, "error": f"Ambiguous: {count} matches found"}

    new_content = current.replace(old_text, new_text, 1)
    _write_file(path, new_content)
    return {"ok": True, "target": target}


def memory_remove(target: str, old_text: str, workspace: str) -> dict:
    """子串匹配删除。"""
    if target not in ("user", "memory"):
        return {"ok": False, "error": f"Invalid target: {target}"}

    fname = "USER.md" if target == "user" else "MEMORY.md"
    path = os.path.join(workspace, fname)
    current = _read_file(path)

    if old_text not in current:
        return {"ok": False, "error": "old_text not found"}

    new_content = current.replace(old_text, "", 1)
    _write_file(path, new_content)
    return {"ok": True, "target": target}


def memory_search(query: str, scopes: dict = None, limit: int = 5) -> dict:
    """Multi-Scope 语义检索（调用 TemporalTree）。"""
    if not MEMORY_WORKSPACE:
        return {"ok": False, "error": "Memory workspace not set"}

    store = MemoryStore(MEMORY_WORKSPACE)
    nodes = store.search_memory(query, scopes, limit)
    return {
        "ok": True,
        "results": [
            {"id": n.id, "content": n.content, "category": n.category,
             "confidence": n.confidence, "status": n.status, "version": n.version}
            for n in nodes
        ]
    }


def memory_supersede(old_node_id: str, new_content: str) -> dict:
    """用新事实取代旧事实。"""
    if not MEMORY_WORKSPACE:
        return {"ok": False, "error": "Memory workspace not set"}

    store = MemoryStore(MEMORY_WORKSPACE)
    node = store.tree.supersede(old_node_id, new_content)
    if node:
        return {"ok": True, "new_id": node.id, "version": node.version}
    return {"ok": False, "error": f"Node not found: {old_node_id}"}


def memory_audit(node_id: str) -> dict:
    """追溯事实的完整版本链。"""
    if not MEMORY_WORKSPACE:
        return {"ok": False, "error": "Memory workspace not set"}

    store = MemoryStore(MEMORY_WORKSPACE)
    trail = store.tree.get_audit_trail(node_id)
    return {
        "ok": True,
        "trail": [
            {"id": n.id, "content": n.content, "version": n.version,
             "status": n.status, "created_at": n.created_at}
            for n in trail
        ]
    }
