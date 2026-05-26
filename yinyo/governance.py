# governance.py — Risk Policy + Secret Scanner v8.1
import re, os
from dataclasses import dataclass

@dataclass
class GateResult:
    action: str  # "allow" | "confirm" | "blocked"
    reason: str = ""
    prompt: str = ""

class RiskPolicy:
    BLOCK_ALWAYS = [
        "delete remote resources",
        "modify provider / API key / config",
        "push / publish externally",
        "payment operations",
    ]
    CONFIRM_REQUIRED = [
        "write files outside workspace",
        "HTTP POST/PUT/PATCH/DELETE",
        "shell commands: rm, chmod, chown, reboot, shutdown, dd, mkfs",
    ]

    def __init__(self, workspace: str = "."):
        self.workspace = workspace

    def gate(self, action_type: str, details: dict = None) -> GateResult:
        if action_type in self.BLOCK_ALWAYS:
            return GateResult("blocked", reason=f"{action_type} blocked by risk policy")
        if action_type in self.CONFIRM_REQUIRED:
            return GateResult("confirm", prompt=f"Confirm {action_type}?")
        return GateResult("allow")

    def gate_for_tool(self, tool_name: str, args: dict) -> GateResult:
        """根据工具名和参数判断风险等级。"""
        path = args.get("path", "")

        # do_write / do_edit / do_patch：检查 workspace 外写
        if tool_name in ("do_write", "do_edit", "do_patch"):
            if path and not self._in_workspace(path):
                return GateResult("blocked", reason=f"Write outside workspace: {path}")
            return GateResult("allow")

        # do_run：检查危险命令
        if tool_name == "do_run":
            cmd = args.get("command", "")
            dangerous = ["rm -rf /", "dd if=", "mkfs", "> /dev/", "chmod 777 /",
                        "reboot", "shutdown", ":(){ :|:& };:"]  # fork bomb
            for d in dangerous:
                if d in cmd:
                    return GateResult("blocked", reason=f"Dangerous command: '{d}' in '{cmd[:80]}'")
            return GateResult("allow")

        # 其他工具默认放行
        return GateResult("allow")

    def _in_workspace(self, path: str) -> bool:
        """检查 path 是否在 workspace 内。"""
        abs_path = os.path.abspath(path)
        abs_workspace = os.path.abspath(self.workspace)
        return abs_path.startswith(abs_workspace)


# Secret patterns (v3.1: BU-03 修复 — 增加无引号格式)
SECRET_PATTERNS = [
    # 引号包围的值（原有）
    r'(?i)(api[_-]?key|token|secret|password|auth)\s*[:=]\s*[\'"][^\'"]+[\'"]',
    # 无引号值（BU-03 修复）：key=value 或 key: value，最少 8 字符防误报
    r'(?i)(api[_-]?key|token|secret|password|auth)\s*[:=]\s*([^\s\'"\n]{8,})',
    # 已知 secret 前缀格式
    r'sk-[a-zA-Z0-9]{20,}',
    r'ghp_[a-zA-Z0-9]{36}',
    r'github_pat_[a-zA-Z0-9_]{36,}',
    r'(?i)Bearer\s+[a-zA-Z0-9\-_\.]{20,}',
    r'glpat-[a-zA-Z0-9\-_]{20,}',
]


def scan_secrets(text: str) -> list:
    """扫描文本中的 secret。返回命中的模式列表。"""
    found = []
    for p in SECRET_PATTERNS:
        for m in re.finditer(p, text):
            found.append({
                "pattern": p[:40],
                "match": m.group()[:30] + "..." if len(m.group()) > 30 else m.group()
            })
    return found


def redact_secrets(text: str) -> str:
    """将文本中的 secret 替换为 [REDACTED]。"""
    for p in SECRET_PATTERNS:
        text = re.sub(p, '[REDACTED]', text)
    return text
