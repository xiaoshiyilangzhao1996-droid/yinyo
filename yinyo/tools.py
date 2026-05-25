# tools.py — 原子工具系统 v3.0（7 个工具 + 完整 evidence 管线）
import os, json, hashlib, subprocess, glob
from typing import Callable, get_type_hints

class Tool:
    def __init__(self, name: str, fn: Callable, schema: dict, permission: str):
        self.name = name; self.fn = fn; self.schema = schema; self.permission = permission

class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}
    def register(self, tool: Tool):
        self._tools[tool.name] = tool
    def get_schemas(self) -> list:
        """返回 OpenAI tool-calling 格式的 tools schema。"""
        return [t.schema for t in self._tools.values()]
    def dispatch(self, name: str, args: dict):
        tool = self._tools.get(name)
        if not tool:
            return {"error": f"Unknown tool: {name}"}
        try:
            return tool.fn(**args)
        except Exception as e:
            return {"error": f"Tool execution error: {type(e).__name__}: {e}"}
    def list(self) -> list:
        return list(self._tools.values())

def tool(permission: str = "ALLOW"):
    def decorator(fn):
        hints = get_type_hints(fn)
        schema = _build_json_schema(fn.__name__, fn.__doc__ or "", hints)
        fn._tool_meta = {"name": fn.__name__, "schema": schema, "permission": permission}
        return fn
    return decorator

def _build_json_schema(name: str, doc: str, hints: dict) -> dict:
    type_map = {str: "string", int: "integer", float: "number", bool: "boolean", dict: "object", list: "array"}
    properties = {}
    required = []
    for pname, ptype in hints.items():
        if pname == "return": continue
        json_type = type_map.get(ptype, "string")
        properties[pname] = {"type": json_type}
        required.append(pname)
    # OpenAI tool-calling 格式（不带 "type": "function" 包装层）
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": doc.strip().split("\n")[0] if doc else "",
            "parameters": {"type": "object", "properties": properties, "required": required}
        }
    }


# ============================================================
# 7 个原子工具
# ============================================================

@tool(permission="ALLOW")
def do_read(path: str, offset: int = 1, limit: int = 500) -> dict:
    """Read a file with line numbers. Returns content and total lines."""
    if not os.path.isfile(path):
        return {"error": f"File not found: {path}"}
    sensitive = {".env", ".key", ".token", ".pem", "credentials", "secrets"}
    if any(s in path.lower() for s in sensitive):
        return {"error": "Access denied: sensitive file"}
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    total = len(lines)
    selection = lines[offset-1:offset-1+limit]
    content = "".join(f"{i+offset:4}|{l}" for i, l in enumerate(selection))
    return {"content": content, "total_lines": total, "shown": len(selection)}


@tool(permission="CONFIRM")
def do_write(path: str, content: str, append: bool = False) -> dict:
    """Write content to a file. Returns bytes written and sha256 hash."""
    mode = "a" if append else "w"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, mode, encoding="utf-8") as f:
        f.write(content)
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        h = hashlib.sha256(f.read()).hexdigest()[:16]
    return {"wrote": len(content.encode("utf-8")), "path": path, "hash": f"sha256:{h}", "size": size}


@tool(permission="ALLOW")
def do_search(query: str, path: str = ".", file_glob: str = "*", mode: str = "content") -> dict:
    """Search file contents (mode='content') or find files by name (mode='files')."""
    results = []
    if mode == "files":
        for f in glob.glob(os.path.join(path, "**", file_glob), recursive=True):
            if os.path.isfile(f):
                results.append({"path": f, "size": os.path.getsize(f)})
        return {"mode": "files", "count": len(results), "results": results[:50]}
    if mode == "content":
        for fp in glob.glob(os.path.join(path, "**", file_glob), recursive=True):
            if not os.path.isfile(fp) or os.path.getsize(fp) > 1_000_000:
                continue
            try:
                with open(fp, "r", encoding="utf-8", errors="replace") as f:
                    for i, line in enumerate(f, 1):
                        if query.lower() in line.lower():
                            results.append({"file": fp, "line": i, "content": line.strip()[:200]})
                            if len(results) >= 50: break
            except: pass
            if len(results) >= 50: break
        return {"mode": "content", "query": query, "count": len(results), "results": results}
    return {"error": f"Unknown mode: {mode}"}


@tool(permission="CONFIRM")
def do_run(command: str, timeout: int = 60, workdir: str = ".") -> dict:
    """Execute a shell command. Returns stdout, stderr, and exit_code."""
    # 危险命令拦截信任 governance.gate_for_tool 层（GAP-7 修复）
    try:
        r = subprocess.run(command, shell=True, capture_output=True, text=True,
                          timeout=timeout, cwd=workdir)
        return {"stdout": r.stdout[-5000:], "stderr": r.stderr[-2000:], "exit_code": r.returncode}
    except subprocess.TimeoutExpired:
        return {"error": f"Timeout after {timeout}s", "exit_code": -1}
    except Exception as e:
        return {"error": str(e), "exit_code": -1}


@tool(permission="ALLOW")
def do_ask(question: str, model: str = "", context: str = "") -> dict:
    """Ask the model a sub-question. Uses DEEPSEEK_API_KEY from environment."""
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        return {"note": "No API key configured", "question": question}
    try:
        import requests as _r
        resp = _r.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model or "deepseek-v4-flash", "messages": [
                {"role": "system", "content": context or "Answer concisely."},
                {"role": "user", "content": question}
            ], "max_tokens": 1024},
            timeout=60
        )
        if resp.status_code == 200:
            return {"answer": resp.json()["choices"][0]["message"]["content"]}
        return {"error": f"API error: {resp.status_code}"}
    except Exception as e:
        return {"error": str(e), "question": question}


# ★ v3.0 新增

@tool(permission="CONFIRM")
def do_edit(path: str, old_string: str, new_string: str, replace_all: bool = False) -> dict:
    """Targeted find-and-replace in a file. Returns sha256 hash for verification.
    
    Args:
        path: File path to edit
        old_string: Exact string to find (must be unique unless replace_all=True)
        new_string: Replacement text (empty string '' to delete)
        replace_all: Replace all occurrences instead of requiring unique match
    """
    if not os.path.isfile(path):
        return {"error": f"File not found: {path}"}
    
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        original = f.read()
    
    count = original.count(old_string)
    if count == 0:
        return {"error": "String not found in file", "searched": old_string[:100]}
    if count > 1 and not replace_all:
        # 找到所有匹配位置
        positions = []
        pos = original.find(old_string)
        while pos != -1:
            line_num = original[:pos].count("\n") + 1
            positions.append({"line": line_num, "position": pos})
            pos = original.find(old_string, pos + 1)
        return {"error": f"Found {count} matches (need unique match or replace_all=True)",
                "matches": positions[:10], "total": count}
    
    new_content = original.replace(old_string, new_string)
    
    # 写回文件
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)
    
    with open(path, "rb") as f:
        h = hashlib.sha256(f.read()).hexdigest()[:16]
    
    # 生成 diff 预览
    diff_lines = []
    old_lines = old_string.split("\n")
    new_lines = new_string.split("\n")
    for ol in old_lines[:3]:
        diff_lines.append(f"- {ol}")
    for nl in new_lines[:3]:
        diff_lines.append(f"+ {nl}")
    
    return {
        "status": "applied",
        "replacements": count if replace_all else 1,
        "path": path,
        "hash": f"sha256:{h}",
        "diff_preview": "\n".join(diff_lines[:10]),
        "chars_replaced": len(old_string) * (count if replace_all else 1),
    }


@tool(permission="CONFIRM")
def do_patch(path: str, patch_content: str) -> dict:
    """Apply a V4A-format patch to a file. Returns sha256 hash for verification.
    
    Format:
        *** Begin Patch
        *** Update File: path/to/file
        @@ context hint @@
         context line
        -removed line
        +added line
        *** End Patch
    
    Multiple hunks supported.
    """
    if not os.path.isfile(path):
        return {"error": f"File not found: {path}"}
    
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        original_lines = f.readlines()
    
    # 解析 V4A patch
    hunks = []
    current_hunk = None
    for line in patch_content.split("\n"):
        if line.startswith("*** Begin Patch") or line.startswith("*** End Patch"):
            continue
        if line.startswith("*** Update File:"):
            continue
        if line.startswith("@@"):
            if current_hunk:
                hunks.append(current_hunk)
            current_hunk = {"context": line.strip(), "changes": []}
            continue
        if current_hunk is not None:
            current_hunk["changes"].append(line)
    if current_hunk and current_hunk["changes"]:
        hunks.append(current_hunk)
    
    if not hunks:
        return {"error": "No valid hunks found in patch"}
    
    # 应用每个 hunk（在原始内容上逐步应用）
    result_lines = list(original_lines)
    for hunk in hunks:
        result_lines = _apply_hunk(result_lines, hunk)
        if result_lines is None:
            return {"error": f"Patch hunk failed: {hunk.get('context', 'unknown')}"}
    
    new_content = "".join(result_lines)
    if new_content == "".join(original_lines):
        return {"error": "Patch applied but no changes made"}
    
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)
    
    with open(path, "rb") as f:
        h = hashlib.sha256(f.read()).hexdigest()[:16]
    
    return {
        "status": "applied",
        "files_changed": 1,
        "hunks": len(hunks),
        "path": path,
        "hash": f"sha256:{h}",
        "lines_changed": len(new_content.split("\n")) - len(original_lines),
    }


def _apply_hunk(lines: list, hunk: dict) -> list | None:
    """Apply a single hunk to lines. Returns modified lines or None on failure."""
    changes = hunk["changes"]
    # 找 context 行定位
    context_lines = [c for c in changes if not c.startswith("-") and not c.startswith("+")]
    if not context_lines:
        # 纯增删的 hunk：所有 - 行删除，所有 + 行追加
        to_remove = set()
        to_add = []
        for c in changes:
            if c.startswith("-"):
                stripped = c[1:]
                for i, l in enumerate(lines):
                    if l.rstrip("\n") == stripped:
                        to_remove.add(i)
            elif c.startswith("+"):
                to_add.append(c[1:] + "\n")
        
        result = [l for i, l in enumerate(lines) if i not in to_remove]
        # 在最后一个删除位置之后添加
        insert_pos = min(to_remove) if to_remove else len(result)
        for a in reversed(to_add):
            result.insert(insert_pos, a)
        return result
    
    # 有 context：精确定位
    first_ctx = context_lines[0].strip() if context_lines[0].startswith(" ") else context_lines[0].lstrip("+- ").strip()
    match_pos = -1
    for i, l in enumerate(lines):
        if first_ctx in l:
            match_pos = i
            break
    
    if match_pos < 0:
        return None  # context 不匹配
    
    # 在匹配位置应用改动
    result = []
    change_idx = 0
    for i in range(len(lines)):
        if i < match_pos:
            result.append(lines[i])
            continue
        # 在 context 区域
        while change_idx < len(changes) and i >= match_pos:
            c = changes[change_idx]
            if c.startswith("-"):
                # 跳过该行（删除）
                change_idx += 1
                if i < len(lines) and lines[i].rstrip("\n") == c[1:]:
                    pass  # 匹配，跳过
            elif c.startswith("+"):
                result.append(c[1:] + "\n")
                change_idx += 1
                continue  # 不消费 lines[i]，继续处理下一个 change
            else:
                # context 行，匹配后消费
                result.append(lines[i] if i < len(lines) else c + "\n")
                change_idx += 1
                break
        else:
            if i < len(lines):
                result.append(lines[i])
            break
    
    # 追加剩余 lines
    result.extend(lines[match_pos + len([c for c in changes if not c.startswith("+")]):])
    # 追加剩余未处理的 + 行
    while change_idx < len(changes):
        c = changes[change_idx]
        if c.startswith("+"):
            result.append(c[1:] + "\n")
        change_idx += 1
    
    return result


# ============================================================
# 注册所有内置工具
# ============================================================

registry = ToolRegistry()
for fn in [do_read, do_write, do_search, do_run, do_ask, do_edit, do_patch]:
    meta = getattr(fn, '_tool_meta', None)
    if meta:
        registry.register(Tool(name=meta["name"], fn=fn, schema=meta["schema"], permission=meta["permission"]))


def load_yaml_tools(yaml_path: str, registry: ToolRegistry) -> int:
    """加载用户自定义 YAML 工具到注册表。"""
    try:
        with open(yaml_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception:
        try:
            import yaml
            with open(yaml_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
        except Exception:
            return 0
    count = 0
    for tdef in config.get('tools', []):
        name = tdef['name']
        perm = tdef.get('permission', 'ALLOW')
        desc = tdef.get('description', '')
        cmd = tdef.get('command', '')
        params = tdef.get('parameters', {})
        def make_fn(cmd=cmd):
            import subprocess as _sp
            def fn(**kwargs):
                expanded = cmd
                for k, v in kwargs.items():
                    expanded = expanded.replace('{' + k + '}', str(v))
                try:
                    r = _sp.run(expanded, shell=True, capture_output=True, text=True, timeout=120)
                    return {'stdout': r.stdout[-5000:], 'stderr': r.stderr[-2000:], 'exit_code': r.returncode}
                except Exception as e:
                    return {'error': str(e), 'exit_code': -1}
            return fn
        schema = {
            'type': 'function',
            'function': {
                'name': name,
                'description': desc,
                'parameters': {'type': 'object', 'properties': params, 'required': list(params.keys())}
            }
        }
        registry.register(Tool(name=name, fn=make_fn(), schema=schema, permission=perm))
        count += 1
    return count


def execute_tool_with_evidence(registry: ToolRegistry, name: str, args: dict,
                               evidence_ledger, governance, run_id: str, step: int) -> dict:
    """★ 审计修复 #10: 执行工具 + Governance Gate + Secret Scan + Evidence Record。完整管线。"""
    # 1. Governance Gate（前置拦截）
    if governance:
        gate = governance.gate_for_tool(name, args)
        if gate.action == "blocked":
            return {"error": f"Blocked by risk policy: {gate.reason}", "_blocked": True}
    
    # 2. 执行工具
    result = registry.dispatch(name, args)
    
    # 3. ★ Secret Scan（后置扫描 + 实际脱敏）
    if governance and not result.get("_blocked"):
        result_str = json.dumps(result, ensure_ascii=False)
        from governance import scan_secrets as _scan_secrets, redact_secrets as _redact_fn
        found = _scan_secrets(result_str)
        if found:
            result["_redacted"] = True
            result["_found_secrets"] = len(found)
            # ★ GAP-4 修复: 对 result 中的字符串字段实际脱敏
            for key in list(result.keys()):
                if isinstance(result[key], str):
                    result[key] = _redact_fn(result[key])
    
    # 4. Evidence Ledger
    evidence_ref = ""
    if evidence_ledger:
        evidence_ref = evidence_ledger.record(run_id, step, name, args, result)
    
    result["_evidence_ref"] = evidence_ref
    return result


# ============================================================
# Memory 工具（v6.0: 对标 Hermes memory tool）
# ============================================================

_memory_workspace = "."  # agent.py 在 init 时设置

def set_memory_workspace(workspace: str):
    """设置 memory 工具的 workspace 路径。"""
    global _memory_workspace
    _memory_workspace = workspace

@tool(permission="ALLOW")
def do_memory(action: str, target: str, content: str = "", old_text: str = "") -> dict:
    """Manage persistent memory. Actions: add, replace, remove.
    Target: 'user' for USER.md, 'memory' for MEMORY.md.
    
    Args:
        action: 'add', 'replace', or 'remove'
        target: 'user' (user profile) or 'memory' (agent notes)
        content: Content to add or replacement text
        old_text: (replace/remove) Substring to match existing entry
    """
    from memory_tool import memory_add, memory_replace, memory_remove
    
    if action == "add":
        return memory_add(target, content, _memory_workspace)
    elif action == "replace":
        return memory_replace(target, old_text, content, _memory_workspace)
    elif action == "remove":
        return memory_remove(target, old_text, _memory_workspace)
    return {"error": f"Unknown action: {action}. Use add, replace, or remove."}

registry.register(Tool(
    name="do_memory",
    fn=do_memory,
    schema=do_memory._tool_meta["schema"],
    permission=do_memory._tool_meta["permission"]
))
