# evidence.py — Evidence Engine v8.1（三态验证 + Write hash 不丢失）
import json, os, re, hashlib
from datetime import datetime, timezone
from dataclasses import dataclass, field
from governance import SECRET_PATTERNS

# v8.1: SECRET_PATTERNS 从 governance 统一导入（消除重复定义）

def _redact(text: str) -> str:
    for p in SECRET_PATTERNS:
        text = re.sub(p, '[REDACTED]', text)
    return text


@dataclass
class VerifyResult:
    status: str  # ★ v3.0 三态: "verified" | "blocked" | "pending"
    reason: str
    evidence_refs: list = field(default_factory=list)


class EvidenceLedger:
    """JSONL append-only evidence ledger。"""
    def __init__(self, run_dir: str):
        self.path = os.path.join(run_dir, "evidence.jsonl")
        os.makedirs(run_dir, exist_ok=True)

    def record(self, run_id: str, step: int, tool: str, args: dict, result: dict) -> str:
        """★ 审计修复 #9: 写入前自动 redact secrets。返回 evidence ref。"""
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
            "step": step,
            "tool": tool,
            "args": self._redact_args(args),
            "result": self._summarize(result),
            "hash": self._hash(result)
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return hashlib.sha256(json.dumps(record).encode()).hexdigest()[:12]

    def _redact_args(self, d: dict) -> dict:
        """Redact 敏感字段。"""
        return {
            k: _redact(str(v)) if any(p in k.lower()
            for p in ["key", "token", "secret", "password", "auth"]) else v
            for k, v in d.items()
        }

    def _summarize(self, result: dict, max_len: int = 200) -> dict:
        s = json.dumps(result, ensure_ascii=False)
        redacted = _redact(s)
        return {"preview": redacted[:max_len] + ("..." if len(redacted) > max_len else ""),
                "size": len(s)}

    def _hash(self, result: dict) -> str:
        return "sha256:" + hashlib.sha256(
            json.dumps(result, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()[:16]


class VerificationGate:
    """★ 审计修复 #1 + #6: Write hash 不丢失（ReAct）+ 三态验证。"""

    def verify(self, outcome: dict) -> VerifyResult:
        tool = outcome.get("tool", "")
        result = outcome.get("result", {})
        expected_hash = result.get("hash", "") or outcome.get("hash", "")

        # ★ 审计修复 #1: ReAct 下 do_write/do_edit/do_patch 返回原生 dict，hash 不丢失
        if tool in ("do_write", "do_edit", "do_patch"):
            path = outcome.get("args", {}).get("path", "") or result.get("path", "")
            if expected_hash and path and os.path.isfile(path):
                with open(path, "rb") as f:
                    actual_hash = "sha256:" + hashlib.sha256(f.read()).hexdigest()[:16]
                if expected_hash != actual_hash:
                    return VerifyResult("blocked",
                        f"Hash mismatch: expected {expected_hash}, got {actual_hash}")

        # Run 验证
        if tool == "do_run":
            ec = result.get("exit_code", 1)
            if ec != 0:
                return VerifyResult("blocked", f"Non-zero exit code: {ec}")

        # Blocked 传播
        if result.get("_blocked"):
            return VerifyResult("blocked",
                result.get("error", "Blocked by risk policy"))

        # ★ 审计修复 #6: pending 状态（需要异步验证时）
        if result.get("_pending"):
            return VerifyResult("pending", "Awaiting async verification")

        return VerifyResult("verified", "")


class RunManifest:
    """每次运行一个 manifest.json。"""
    def __init__(self, run_dir: str):
        self.path = os.path.join(run_dir, "manifest.json")

    def create(self, run_id: str, task: str) -> dict:
        m = {
            "run_id": run_id,
            "task": task,
            "started": datetime.now(timezone.utc).isoformat(),
            "status": "running",
            "steps": 0,
            "tools_used": [],
            "verification": {
                "verified_steps": 0,
                "blocked_steps": 0,
                "final_status": "pending"
            },
            "evidence_file": f"runs/{run_id}/evidence.jsonl",
            "blocked_reason": None
        }
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(m, f, indent=2, ensure_ascii=False)
        return m

    def update(self, **kwargs):
        with open(self.path) as f:
            m = json.load(f)
        m.update(kwargs)
        with open(self.path, "w") as f:
            json.dump(m, f, indent=2, ensure_ascii=False)
        return m
