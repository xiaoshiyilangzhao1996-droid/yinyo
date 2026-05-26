# tools.py — 原子工具系统 v8.1（BU-01/BU-02 安全修复）
import os, json, hashlib, subprocess, glob, re
from typing import Callable, get_type_hints

# ============================================================
# 路径安全（v8.1: BU-01/BU-02 修复）
# ============================================================

_tool_workspace = os.path.abspath(".")

# v8.1: 由 agent.py 在 init 时设置，供 delegate_task 使用（替代 __main__ 注入）
_yinyo_agent = None

def set_tool_workspace(workspace: str):
    """设置工具层的 workspace 路径，用于路径穿越防护。agent.py 在 init 时调用。"""
    global _tool_workspace
    _tool_workspace = os.path.abspath(workspace)

def _validate_path(path: str) -> str:
    """安全路径校验：拒绝绝对路径 + 路径穿越。返回规范化后的安全路径。
    
    规则：
    1. 拒绝绝对路径（如 /etc/passwd, C:\\Windows\\...）
    2. realpath 规范化 + workspace 范围检查
    """
    # 规则1: 拒绝绝对路径（含 Unix 风格，如 /etc/passwd）
    if os.path.isabs(path) or path.startswith("/"):
        raise PermissionError(f"Absolute paths not allowed: {path}")
    
    # 规则2: realpath 规范化 + workspace 范围检查
    safe = os.path.realpath(os.path.join(_tool_workspace, path))
    ws = os.path.realpath(_tool_workspace)
    if not safe.startswith(ws + os.sep) and safe != ws:
        raise PermissionError(f"Path traversal blocked: {path}")
    
    return safe

# 危险命令模式（BU-02: 内联检查，防止直接 import do_run 绕过 governance）
_DANGEROUS_COMMANDS = [
    r"rm\s+-rf\s+/", r"dd\s+if=", r"mkfs", r">\s*/dev/", r"chmod\s+777\s+/",
    r"\breboot\b", r"\bshutdown\b", r":\(\)\s*\{\s*:\|:&\s*\};:",
    r"curl.*\|.*sh", r"wget.*\|.*sh",
]

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
    def execute(self, name: str, args: dict) -> dict:
        """v8.0: delegate.py 使用的同义方法。"""
        return self.dispatch(name, args)
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
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": doc.strip().split("\n")[0] if doc else "",
            "parameters": {"type": "object", "properties": properties, "required": required}
        }
    }


# ============================================================
# 8 个原子工具（v8.1: 全部内置路径校验）
# ============================================================

@tool(permission="ALLOW")
def do_read(path: str, offset: int = 1, limit: int = 500) -> dict:
    """Read a file with line numbers. Returns content and total lines."""
    try:
        safe = _validate_path(path)
    except PermissionError as e:
        return {"error": str(e)}
    if not os.path.isfile(safe):
        return {"error": f"File not found: {path}"}
    sensitive = {".env", ".key", ".token", ".pem", "credentials", "secrets"}
    if any(s in path.lower() for s in sensitive):
        return {"error": "Access denied: sensitive file"}
    with open(safe, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    total = len(lines)
    selection = lines[offset-1:offset-1+limit]
    content = "".join(f"{i+offset:4}|{l}" for i, l in enumerate(selection))
    return {"content": content, "total_lines": total, "shown": len(selection)}


@tool(permission="CONFIRM")
def do_write(path: str, content: str, append: bool = False) -> dict:
    """Write content to a file. Returns bytes written and sha256 hash."""
    try:
        safe = _validate_path(path)
    except PermissionError as e:
        return {"error": str(e)}
    mode = "a" if append else "w"
    os.makedirs(os.path.dirname(safe) or ".", exist_ok=True)
    with open(safe, mode, encoding="utf-8") as f:
        f.write(content)
    size = os.path.getsize(safe)
    with open(safe, "rb") as f:
        h = hashlib.sha256(f.read()).hexdigest()[:16]
    return {"wrote": len(content.encode("utf-8")), "path": path, "hash": f"sha256:{h}", "size": size}


@tool(permission="ALLOW")
def do_search(query: str, path: str = ".", file_glob: str = "*", mode: str = "content") -> dict:
    """Search file contents (mode='content') or find files by name (mode='files')."""
    try:
        safe_path = _validate_path(path)
    except PermissionError as e:
        return {"error": str(e)}
    results = []
    if mode == "files":
        for f in glob.glob(os.path.join(safe_path, "**", file_glob), recursive=True):
            if os.path.isfile(f):
                results.append({"path": f, "size": os.path.getsize(f)})
        return {"mode": "files", "count": len(results), "results": results[:50]}
    if mode == "content":
        for fp in glob.glob(os.path.join(safe_path, "**", file_glob), recursive=True):
            if not os.path.isfile(fp) or os.path.getsize(fp) > 1_000_000:
                continue
            try:
                with open(fp, "r", encoding="utf-8", errors="replace") as f:
                    for i, line in enumerate(f, 1):
                        if query.lower() in line.lower():
                            results.append({"file": fp, "line": i, "content": line.strip()[:200]})
                            if len(results) >= 50: break
            except (OSError, UnicodeDecodeError): pass
            if len(results) >= 50: break
        return {"mode": "content", "query": query, "count": len(results), "results": results}
    return {"error": f"Unknown mode: {mode}"}


@tool(permission="CONFIRM")
def do_run(command: str, timeout: int = 60, workdir: str = ".") -> dict:
    """Execute a shell command. Returns stdout, stderr, and exit_code."""
    # v8.1 BU-02修复: 内联危险命令检查（防止直接 import do_run 绕过 governance）
    for d in _DANGEROUS_COMMANDS:
        if re.search(d, command):
            return {"error": f"Blocked dangerous command: {command[:100]}", "exit_code": -1}
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
    try:
        safe = _validate_path(path)
    except PermissionError as e:
        return {"error": str(e)}
    if not os.path.isfile(safe):
        return {"error": f"File not found: {path}"}
    
    with open(safe, "r", encoding="utf-8", errors="replace") as f:
        original = f.read()
    
    count = original.count(old_string)
    if count == 0:
        return {"error": "String not found in file", "searched": old_string[:100]}
    if count > 1 and not replace_all:
        positions = []
        pos = original.find(old_string)
        while pos != -1:
            line_num = original[:pos].count("\n") + 1
            positions.append({"line": line_num, "position": pos})
            pos = original.find(old_string, pos + 1)
        return {"error": f"Found {count} matches (need unique match or replace_all=True)",
                "matches": positions[:10], "total": count}
    
    new_content = original.replace(old_string, new_string)
    
    with open(safe, "w", encoding="utf-8") as f:
        f.write(new_content)
    
    with open(safe, "rb") as f:
        h = hashlib.sha256(f.read()).hexdigest()[:16]
    
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
    try:
        safe = _validate_path(path)
    except PermissionError as e:
        return {"error": str(e)}
    if not os.path.isfile(safe):
        return {"error": f"File not found: {path}"}
    
    with open(safe, "r", encoding="utf-8", errors="replace") as f:
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
    
    result_lines = list(original_lines)
    for hunk in hunks:
        result_lines = _apply_hunk(result_lines, hunk)
        if result_lines is None:
            return {"error": f"Patch hunk failed: {hunk.get('context', 'unknown')}"}
    
    new_content = "".join(result_lines)
    if new_content == "".join(original_lines):
        return {"error": "Patch applied but no changes made"}
    
    with open(safe, "w", encoding="utf-8") as f:
        f.write(new_content)
    
    with open(safe, "rb") as f:
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
    context_lines = [c for c in changes if not c.startswith("-") and not c.startswith("+")]
    if not context_lines:
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
        insert_pos = min(to_remove) if to_remove else len(result)
        for a in reversed(to_add):
            result.insert(insert_pos, a)
        return result
    
    first_ctx = context_lines[0].strip() if context_lines[0].startswith(" ") else context_lines[0].lstrip("+- ").strip()
    match_pos = -1
    for i, l in enumerate(lines):
        if first_ctx in l:
            match_pos = i
            break
    
    if match_pos < 0:
        return None
    
    result = []
    change_idx = 0
    for i in range(len(lines)):
        if i < match_pos:
            result.append(lines[i])
            continue
        while change_idx < len(changes) and i >= match_pos:
            c = changes[change_idx]
            if c.startswith("-"):
                change_idx += 1
                if i < len(lines) and lines[i].rstrip("\n") == c[1:]:
                    pass
            elif c.startswith("+"):
                result.append(c[1:] + "\n")
                change_idx += 1
                continue
            else:
                result.append(lines[i] if i < len(lines) else c + "\n")
                change_idx += 1
                break
        else:
            if i < len(lines):
                result.append(lines[i])
            break
    
    result.extend(lines[match_pos + len([c for c in changes if not c.startswith("+")]):])
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

# ── v8.0 新增工具 ──

@tool(permission="ALLOW")
def do_vision(image_source: str, query: str = "请详细描述这张图片的内容") -> dict:
    """Analyze an image and return a text description. Works with local files, URLs, or base64.

    Args:
        image_source: Local file path, image URL, or base64 data URL
        query: What to ask about the image (default: detailed description)
    """
    from vision_adapter import get_vision_adapter
    adapter = get_vision_adapter()
    result = adapter.describe(image_source, query)
    return result

registry.register(Tool(
    name="do_vision",
    fn=do_vision,
    schema=do_vision._tool_meta["schema"],
    permission=do_vision._tool_meta["permission"]
))


@tool(permission="ALLOW")
def delegate_task(goal: str, context: str = "") -> dict:
    """Delegate a sub-task to a worker agent. Returns the worker's result.

    Use this for parallel independent tasks. Multiple delegate_task calls
    can run concurrently via parallel tool calls.

    Args:
        goal: The task description for the worker agent
        context: Additional context (optional, parent context is auto-shared)
    """
    from delegate import SubAgent
    agent = _yinyo_agent
    if not agent:
        return {"error": "delegate_task: no parent agent found"}

    sub = SubAgent(agent.model, agent._tool_registry, max_steps=20)
    result = sub.run(
        goal=goal,
        parent_messages=agent.context.messages,
        parent_workspace=agent.workspace,
    )
    return {
        "result": result.result,
        "steps": result.steps,
        "status": result.status,
        "run_id": result.run_id,
        "tool_traces_count": len(result.tool_traces),
        "error": result.error,
    }

registry.register(Tool(
    name="delegate_task",
    fn=delegate_task,
    schema=delegate_task._tool_meta["schema"],
    permission=delegate_task._tool_meta["permission"]
))
