# evolution.py — 技能结晶与自演化
import os, json, hashlib
from datetime import datetime, timezone
from enum import Enum
from dataclasses import dataclass, field

class SkillStatus(Enum):
    DRAFT = "draft"
    PROVEN = "proven"
    STABLE = "stable"

@dataclass
class Skill:
    name: str
    status: SkillStatus = SkillStatus.DRAFT
    activation_count: int = 0
    blocked_count: int = 0
    created_at: str = ""
    last_used: str = ""
    version: str = "0.1.0"

class SkillCrystallizer:
    """检测工具序列模式，自动结晶为 Skill。"""
    def __init__(self, workspace: str):
        self.workspace = workspace
        self.patterns: dict[str, int] = {}
        os.makedirs(os.path.join(workspace, "skills"), exist_ok=True)

    def observe(self, tool_sequence: list) -> Skill | None:
        """每次任务结束后调用，检测是否有可结晶的序列。"""
        if len(tool_sequence) < 3:
            return None
        seq_hash = hashlib.sha256("→".join(tool_sequence).encode()).hexdigest()[:8]
        self.patterns[seq_hash] = self.patterns.get(seq_hash, 0) + 1
        if self.patterns[seq_hash] >= 3:
            return self._crystallize(seq_hash, tool_sequence)
        return None

    def _crystallize(self, seq_hash: str, tools: list) -> Skill:
        skill_dir = os.path.join(self.workspace, "skills", seq_hash)
        os.makedirs(skill_dir, exist_ok=True)
        md = f"# Skill: {seq_hash}\nstatus: draft\nactivation_count: 3\ntools: {tools}\n\n## 工具序列\n" + \
             "".join(f"{i+1}. {t}\n" for i, t in enumerate(tools))
        with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
            f.write(md)
        now = datetime.now(timezone.utc).isoformat()
        meta = {"name": seq_hash, "status": "draft", "tools": tools,
                "activation_count": 3, "created_at": now}
        with open(os.path.join(skill_dir, "meta.json"), "w") as f:
            json.dump(meta, f, indent=2)
        return Skill(name=seq_hash, status=SkillStatus.DRAFT, activation_count=3,
                     created_at=now, last_used=now)

    def promote(self, skill: Skill) -> Skill:
        if skill.status == SkillStatus.DRAFT and skill.activation_count >= 5:
            skill.status = SkillStatus.PROVEN
            skill.version = "0.5.0"
        elif skill.status == SkillStatus.PROVEN and skill.activation_count >= 10:
            skill.status = SkillStatus.STABLE
            skill.version = "1.0.0"
        self._update_meta(skill)
        return skill

    def _update_meta(self, skill: Skill):
        """写回 meta.json。"""
        mp = os.path.join(self.workspace, "skills", skill.name, "meta.json")
        if os.path.exists(mp):
            with open(mp, 'w') as f:
                json.dump({"name": skill.name, "status": skill.status.value,
                           "activation_count": skill.activation_count,
                           "blocked_count": skill.blocked_count,
                           "version": skill.version, "last_used": skill.last_used}, f, indent=2)

    def increment_blocked(self, name: str):
        """递增指定技能的 blocked 计数。"""
        mp = os.path.join(self.workspace, "skills", name, "meta.json")
        if os.path.exists(mp):
            with open(mp) as f:
                meta = json.load(f)
            meta["blocked_count"] = meta.get("blocked_count", 0) + 1
            with open(mp, 'w') as f:
                json.dump(meta, f, indent=2)

class ChangeManifest:
    """Agent 自省：记录 Agent 自身的变化（技能结晶、记忆更新、配置变更）。"""
    def __init__(self, workspace: str):
        self.path = os.path.join(workspace, "changes.jsonl")

    def record(self, change_type: str, detail: dict):
        entry = {"ts": datetime.now(timezone.utc).isoformat(), "type": change_type, "detail": detail}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

@dataclass
class CheckItem:
    item: str
    level: str  # PASS / WARN / FAIL
    reason: str = ""

@dataclass
class SelfCheckReport:
    passed: bool
    checks: list  # list[CheckItem]
    summary: str

class SelfCheck:
    """启动时自检 Agent 状态。"""
    def __init__(self, workspace: str):
        self.workspace = workspace

    def run(self) -> SelfCheckReport:
        checks = []
        for d in ["skills", "runs", "cache"]:
            path = os.path.join(self.workspace, d)
            if not os.path.isdir(path):
                checks.append(CheckItem(f"missing_dir:{d}", "FAIL", f"Directory {d} not found"))
        for f in ["YINYO.md", "SOUL.md"]:
            if not os.path.isfile(os.path.join(self.workspace, f)):
                checks.append(CheckItem(f"missing_memory:{f}", "WARN", f"Memory file {f} not found"))
        
        # 技能版本一致性检查
        import glob as _glob
        for mp in _glob.glob(os.path.join(self.workspace, "skills", "*", "meta.json")):
            meta = json.load(open(mp))
            if meta.get("status") == "draft" and meta.get("activation_count", 0) > 5:
                checks.append(CheckItem(f"stale_skill:{meta['name']}", "WARN",
                               f"Skill stuck in draft despite {meta['activation_count']} activations"))

        # Evidence 完整性检查
        for ef in _glob.glob(os.path.join(self.workspace, "runs", "*", "evidence.jsonl")):
            if os.path.getsize(ef) == 0:
                checks.append(CheckItem(f"empty_evidence:{os.path.basename(os.path.dirname(ef))}", "WARN", "Evidence file is empty"))

        fails = sum(1 for c in checks if c.level == "FAIL")
        warns = sum(1 for c in checks if c.level == "WARN")
        return SelfCheckReport(
            passed=fails == 0,
            checks=checks,
            summary=f"{fails} FAIL, {warns} WARN, {len(checks)-fails-warns} PASS"
        )
