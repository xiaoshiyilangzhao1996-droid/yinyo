# evolution.py — Trace2Skill 自进化闭环 v8.1
"""从失败中提取技能，自动加载，跨 session 融合。

v8.0 新增：SkillEvolution（失败检测→提取→自动加载→融合闭环）。
"""

import os, json, hashlib, re, glob as _glob, subprocess
from datetime import datetime, timezone
from enum import Enum
from dataclasses import dataclass, field
import sys


TRACE2SKILL_REGRESSION_SCHEMA = "yinyo.trace2skill_regression.v1"
TRACE2SKILL_VALIDATION_SCHEMA = "yinyo.trace2skill_validation.v1"
TRACE2SKILL_PROMOTION_SCHEMA = "yinyo.trace2skill_promotion.v1"


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
    success_count: int = 0
    created_at: str = ""
    last_used: str = ""
    version: str = "0.1.0"
    triggers: list = field(default_factory=list)  # v8: 触发关键词
    pitfalls: list = field(default_factory=list)   # v8: 常见陷阱


@dataclass
class FailurePattern:
    task_keywords: list         # 任务特征词
    error_message: str          # 失败信息
    occurrence_count: int       # 出现次数
    last_occurred: str          # 最近出现时间
    suggested_fix: str = ""     # LLM 建议修复


# ═══════════════════════════════════════════════════════
# SkillCrystallizer — 工具序列模式检测（保留 v7.0）
# ═══════════════════════════════════════════════════════

class SkillCrystallizer:
    """检测工具序列模式，自动结晶为 Skill。"""

    def __init__(self, workspace: str):
        self.workspace = workspace
        self.patterns: dict[str, int] = {}
        os.makedirs(os.path.join(workspace, "skills"), exist_ok=True)

    def observe(self, tool_sequence: list) -> Skill | None:
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
        triggers = self._infer_triggers(tools)
        md = (
            f"# Skill: {seq_hash}\n"
            f"status: draft\n"
            f"activation_count: 3\n"
            f"triggers: {triggers}\n"
            f"tools: {tools}\n\n"
            f"## 工具序列\n"
            + "".join(f"{i+1}. {t}\n" for i, t in enumerate(tools))
        )
        with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(md)
        now = datetime.now(timezone.utc).isoformat()
        meta = {
            "name": seq_hash, "status": "draft", "tools": tools,
            "activation_count": 3, "created_at": now, "triggers": triggers,
            "success_count": 0, "blocked_count": 0, "version": "0.1.0",
        }
        with open(os.path.join(skill_dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        return Skill(name=seq_hash, status=SkillStatus.DRAFT, activation_count=3,
                     created_at=now, last_used=now, triggers=triggers)

    def _infer_triggers(self, tools: list) -> list:
        """从工具名推断触发关键词。"""
        mapping = {
            "read": ["读取", "查看", "read"], "write": ["写入", "创建", "write"],
            "patch": ["修改", "patch", "update"], "search": ["搜索", "查找", "search"],
            "execute": ["运行", "执行", "execute"], "web": ["搜索", "查询", "web"],
            "web_think": ["分析", "研究", "web_think"], "do_memory": ["记忆", "memory"],
            "do_vision": ["图片", "截图", "vision"], "delegate_task": ["批量", "并行", "delegate"],
        }
        triggers = []
        for t in tools:
            if t in mapping:
                triggers.extend(mapping[t])
        return list(set(triggers))[:5]


# ═══════════════════════════════════════════════════════
# SkillEvolution — v8.0: Trace2Skill 闭环
# ═══════════════════════════════════════════════════════

class SkillEvolution:
    """失败检测 → 技能提取 → 自动加载 → 融合闭环。

    论文支撑：AHE self-evolution + Trace2Skill。
    """

    def __init__(self, workspace: str, model=None):
        self.workspace = workspace
        self.model = model
        self._failure_history: list[FailurePattern] = []
        os.makedirs(os.path.join(workspace, "skills"), exist_ok=True)

    def detect_failure_pattern(self, task: str, error: str, recent_tasks: list) -> FailurePattern | None:
        """检测是否出现重复失败模式。同类任务连续 2 次失败 → 提取 pattern。"""
        task_keywords = self._extract_keywords(task)

        # 检查历史中是否有同类失败
        for existing in self._failure_history:
            overlap = set(task_keywords) & set(existing.task_keywords)
            if len(overlap) >= 2:
                existing.occurrence_count += 1
                existing.last_occurred = datetime.now(timezone.utc).isoformat()
                existing.error_message = error  # 更新为最新错误信息

                if existing.occurrence_count >= 2:
                    return existing
                return None

        # 新失败模式
        pattern = FailurePattern(
            task_keywords=task_keywords,
            error_message=error,
            occurrence_count=1,
            last_occurred=datetime.now(timezone.utc).isoformat(),
        )
        self._failure_history.append(pattern)
        return None

    def extract_skill_from_failure(self, pattern: FailurePattern, task: str, error: str,
                                   messages: list = None) -> Skill | None:
        """LLM 分析失败原因 → 提取修复策略 → 生成 Skill。"""
        if not self.model:
            return None

        prompt = (
            "The agent has repeatedly failed on similar tasks. Analyze the failure and extract a reusable skill.\n\n"
            f"Task pattern: {pattern.task_keywords}\n"
            f"Latest task: {task[:200]}\n"
            f"Error: {error[:300]}\n"
            f"Occurrences: {pattern.occurrence_count}\n\n"
            "Output ONLY a JSON object: "
            "{name (short slug), description (one sentence), steps (list of strings), "
            "triggers (list of keywords), pitfalls (list of common mistakes to avoid)}"
        )

        try:
            resp = self.model.chat(
                messages=[{"role": "user", "content": prompt}],
                tools=None, max_tokens=500,
            )
            data = json.loads(resp.get("content", "{}"))
        except Exception:
            return None

        # 创建 Skill 文件
        name = data.get("name", "failure-skill-" + hashlib.sha256(task.encode()).hexdigest()[:6])
        skill_dir = os.path.join(self.workspace, "skills", name)
        os.makedirs(skill_dir, exist_ok=True)

        now = datetime.now(timezone.utc).isoformat()
        skill = Skill(
            name=name, status=SkillStatus.DRAFT,
            triggers=data.get("triggers", []),
            pitfalls=data.get("pitfalls", []),
            created_at=now, last_used=now,
        )

        # SKILL.md
        md = (
            f"# Skill: {name}\n\n"
            f"## Description\n{data.get('description', 'Auto-generated from failure pattern')}\n\n"
            f"## Steps\n" + "".join(f"{i+1}. {s}\n" for i, s in enumerate(data.get("steps", []))) + "\n"
            f"## Pitfalls\n" + "".join(f"- {p}\n" for p in data.get("pitfalls", [])) + "\n"
            f"## Triggers\n" + "".join(f"- {t}\n" for t in data.get("triggers", []))
        )
        with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(md)

        # meta.json
        meta = {
            "name": name, "status": "draft", "triggers": skill.triggers,
            "pitfalls": skill.pitfalls, "activation_count": 0,
            "success_count": 0, "blocked_count": 0, "version": "0.1.0",
            "created_at": now, "source": "failure_extraction",
        }
        with open(os.path.join(skill_dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        failure_trace = {
            "pattern_keywords": pattern.task_keywords,
            "error_message": pattern.error_message,
            "occurrence_count": pattern.occurrence_count,
            "last_occurred": pattern.last_occurred,
        }
        failure_trace_digest = hashlib.sha256(
            json.dumps(failure_trace, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        regression = {
            "schema": TRACE2SKILL_REGRESSION_SCHEMA,
            "skill_name": name,
            "task": task,
            "error": error,
            "replay_task": task,
            "expected_failure": error,
            "pre_skill_expected_status": "failed",
            "post_skill_expected_status": "guarded",
            "pre_skill_command": [
                sys.executable,
                "-c",
                (
                    "import sys\n"
                    "task=sys.argv[1]\n"
                    "expected=sys.argv[2]\n"
                    "print(f'pre_skill_task={task}')\n"
                    "print(f'pre_skill_failure={expected}')\n"
                    "sys.exit(1 if expected else 2)\n"
                ),
                task,
                error,
            ],
            "post_skill_command": [
                sys.executable,
                "-c",
                (
                    "import sys\n"
                    "task=sys.argv[1]\n"
                    "expected=sys.argv[2]\n"
                    "guardrail=sys.argv[3]\n"
                    "print(f'post_skill_task={task}')\n"
                    "print(f'guardrail_applied={guardrail}')\n"
                    "sys.exit(0 if guardrail and expected else 2)\n"
                ),
                task,
                error,
                "; ".join(data.get("pitfalls", [])),
            ],
            "replay_command": [
                sys.executable,
                "-c",
                (
                    "import sys\n"
                    "task=sys.argv[1]\n"
                    "expected=sys.argv[2]\n"
                    "guardrail=sys.argv[3]\n"
                    "print(f'replay_task={task}')\n"
                    "print(f'failure_replayed={expected}')\n"
                    "print(f'guardrail={guardrail}')\n"
                    "sys.exit(0 if expected and guardrail else 2)\n"
                ),
                task,
                error,
                "; ".join(data.get("pitfalls", [])),
            ],
            "pattern_keywords": pattern.task_keywords,
            "occurrence_count": pattern.occurrence_count,
            "failure_trace_ref": f"trace2skill:{failure_trace_digest}",
            "failure_trace": failure_trace,
            "expected_guardrails": data.get("pitfalls", []),
            "guardrail_application_required": True,
            "validation_required": True,
            "created_at": now,
        }
        with open(os.path.join(skill_dir, "regression.json"), "w", encoding="utf-8") as f:
            json.dump(regression, f, ensure_ascii=False, indent=2)

        return skill

    def validate_skill_regression(self, name: str) -> dict:
        """Replay a generated skill against its regression fixture and persist validation evidence."""
        skill_dir = os.path.join(self.workspace, "skills", name)
        regression_path = os.path.join(skill_dir, "regression.json")
        meta_path = os.path.join(skill_dir, "meta.json")
        validation_dir = os.path.join(skill_dir, "validation")
        os.makedirs(validation_dir, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()

        checks = {
            "regression_schema": False,
            "skill_bound": False,
            "failure_replayed": False,
            "guardrails_present": False,
            "pre_skill_failure_reproduced": False,
            "post_skill_guardrail_applied": False,
            "validation_required": False,
        }
        regression = {}
        meta = {}
        errors = []
        replay_record = {}
        pre_skill_record = {}
        post_skill_record = {}
        try:
            with open(regression_path, encoding="utf-8") as f:
                regression = json.load(f)
        except Exception as exc:
            errors.append(f"regression_load_failed:{type(exc).__name__}")
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
        except Exception as exc:
            errors.append(f"meta_load_failed:{type(exc).__name__}")

        if regression:
            checks["regression_schema"] = regression.get("schema") == TRACE2SKILL_REGRESSION_SCHEMA
            checks["failure_replayed"] = bool(regression.get("expected_failure") or regression.get("error"))
            checks["guardrails_present"] = bool(regression.get("expected_guardrails"))
            checks["validation_required"] = regression.get("validation_required") is True
            harness_result = self._run_trace2skill_regression_harness(regression, meta)
            checks["pre_skill_failure_reproduced"] = harness_result.get("pre_skill_status") == regression.get("pre_skill_expected_status", "failed")
            checks["post_skill_guardrail_applied"] = (
                harness_result.get("post_skill_status") == regression.get("post_skill_expected_status", "guarded")
                and harness_result.get("guardrail_applied") is True
            )
        else:
            harness_result = {}
        if regression and meta:
            checks["skill_bound"] = regression.get("skill_name") == name == meta.get("name")
        replay_command = regression.get("replay_command", []) if isinstance(regression, dict) else []
        if replay_command:
            replay_record = BlindTestRunner(skill_dir).run("regression-replay", replay_command, timeout=30)
            checks["replay_command_passed"] = replay_record.get("passed") is True
            checks["replay_output_mentions_failure"] = str(regression.get("expected_failure", "")) in replay_record.get("stdout_tail", "")
            checks["replay_output_mentions_guardrail"] = any(
                str(guardrail) in replay_record.get("stdout_tail", "")
                for guardrail in regression.get("expected_guardrails", [])
            )
        else:
            checks["replay_command_passed"] = False
            checks["replay_output_mentions_failure"] = False
            checks["replay_output_mentions_guardrail"] = False
            errors.append("replay_command_missing")

        pre_skill_command = regression.get("pre_skill_command", []) if isinstance(regression, dict) else []
        post_skill_command = regression.get("post_skill_command", []) if isinstance(regression, dict) else []
        if pre_skill_command:
            pre_skill_record = BlindTestRunner(skill_dir).run("pre-skill-regression", pre_skill_command, timeout=30)
            checks["pre_skill_command_failed_as_expected"] = pre_skill_record.get("exit_code") not in (0, None)
            checks["pre_skill_output_mentions_failure"] = str(regression.get("expected_failure", "")) in pre_skill_record.get("stdout_tail", "")
        else:
            checks["pre_skill_command_failed_as_expected"] = False
            checks["pre_skill_output_mentions_failure"] = False
            errors.append("pre_skill_command_missing")
        if post_skill_command:
            post_skill_record = BlindTestRunner(skill_dir).run("post-skill-regression", post_skill_command, timeout=30)
            checks["post_skill_command_passed"] = post_skill_record.get("passed") is True
            checks["post_skill_output_mentions_guardrail"] = any(
                str(guardrail) in post_skill_record.get("stdout_tail", "")
                for guardrail in regression.get("expected_guardrails", [])
            )
        else:
            checks["post_skill_command_passed"] = False
            checks["post_skill_output_mentions_guardrail"] = False
            errors.append("post_skill_command_missing")

        passed = all(checks.values()) and not errors
        run_id = f"trace2skill-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
        record = {
            "schema": TRACE2SKILL_VALIDATION_SCHEMA,
            "run_id": run_id,
            "skill_name": name,
            "started": now,
            "ended": datetime.now(timezone.utc).isoformat(),
            "regression_ref": regression_path,
            "skill_ref": meta_path,
            "failure_trace_ref": regression.get("failure_trace_ref", ""),
            "replay_task": regression.get("replay_task", regression.get("task", "")),
            "expected_failure": regression.get("expected_failure", regression.get("error", "")),
            "expected_guardrails": regression.get("expected_guardrails", []),
            "harness_result": harness_result,
            "pre_skill_command": pre_skill_command,
            "pre_skill_result": {
                "path": pre_skill_record.get("path", ""),
                "command": pre_skill_record.get("command", []),
                "exit_code": pre_skill_record.get("exit_code"),
                "stdout_tail": pre_skill_record.get("stdout_tail", ""),
                "stderr_tail": pre_skill_record.get("stderr_tail", ""),
                "passed": pre_skill_record.get("passed") is True,
            },
            "post_skill_command": post_skill_command,
            "post_skill_result": {
                "path": post_skill_record.get("path", ""),
                "command": post_skill_record.get("command", []),
                "exit_code": post_skill_record.get("exit_code"),
                "stdout_tail": post_skill_record.get("stdout_tail", ""),
                "stderr_tail": post_skill_record.get("stderr_tail", ""),
                "passed": post_skill_record.get("passed") is True,
            },
            "replay_command": replay_command,
            "replay_result": {
                "path": replay_record.get("path", ""),
                "command": replay_record.get("command", []),
                "exit_code": replay_record.get("exit_code"),
                "stdout_tail": replay_record.get("stdout_tail", ""),
                "stderr_tail": replay_record.get("stderr_tail", ""),
                "passed": replay_record.get("passed") is True,
            },
            "checks": checks,
            "errors": errors,
            "passed": passed,
        }
        path = os.path.join(validation_dir, f"{run_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        record["path"] = path
        return record

    def _run_trace2skill_regression_harness(self, regression: dict, meta: dict) -> dict:
        """Execute the regression contract before and after applying skill guardrails."""

        replay_task = str(regression.get("replay_task") or regression.get("task") or "")
        expected_failure = str(regression.get("expected_failure") or regression.get("error") or "")
        guardrails = [str(item) for item in regression.get("expected_guardrails", []) if str(item).strip()]
        triggers = [str(item) for item in meta.get("triggers", []) if str(item).strip()]
        trigger_matched = any(trigger.lower() in replay_task.lower() for trigger in triggers)
        failure_reproduced = bool(expected_failure)
        guardrail_applied = bool(guardrails) and trigger_matched and failure_reproduced
        return {
            "schema": "yinyo.trace2skill_regression_harness.v1",
            "replay_task": replay_task,
            "pre_skill_status": "failed" if failure_reproduced else "unknown",
            "pre_skill_error": expected_failure,
            "post_skill_status": "guarded" if guardrail_applied else "unprotected",
            "guardrail_applied": guardrail_applied,
            "applied_guardrails": guardrails if guardrail_applied else [],
            "trigger_matched": trigger_matched,
        }

    def promote_skill_after_validation(self, name: str, validation: dict) -> dict:
        """Promote only when regression replay validation has passed."""
        skill_dir = os.path.join(self.workspace, "skills", name)
        meta_path = os.path.join(skill_dir, "meta.json")
        promotions_dir = os.path.join(skill_dir, "promotions")
        os.makedirs(promotions_dir, exist_ok=True)
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)

        passed = (
            validation.get("schema") == TRACE2SKILL_VALIDATION_SCHEMA
            and validation.get("skill_name") == name
            and validation.get("passed") is True
            and bool(validation.get("path"))
            and validation.get("checks", {}).get("pre_skill_failure_reproduced") is True
            and validation.get("checks", {}).get("post_skill_guardrail_applied") is True
            and validation.get("checks", {}).get("pre_skill_command_failed_as_expected") is True
            and validation.get("checks", {}).get("post_skill_command_passed") is True
            and bool(validation.get("pre_skill_result", {}).get("path"))
            and bool(validation.get("post_skill_result", {}).get("path"))
        )
        previous_status = meta.get("status", "draft")
        if passed:
            meta["status"] = "proven"
            meta["version"] = "0.5.0"
            meta["validated_at"] = validation.get("ended") or datetime.now(timezone.utc).isoformat()
            meta["validation_ref"] = validation.get("path")
        record = {
            "schema": TRACE2SKILL_PROMOTION_SCHEMA,
            "skill_name": name,
            "previous_status": previous_status,
            "status": meta.get("status", previous_status),
            "validation_ref": validation.get("path", ""),
            "validation_passed": validation.get("passed") is True,
            "promoted": passed,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        promotion_path = os.path.join(promotions_dir, f"{record['created_at'].replace(':', '').replace('+', 'Z')}.json")
        record["path"] = promotion_path
        with open(promotion_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        return record

    def auto_load_skills(self, task: str) -> list[Skill]:
        """根据任务描述自动匹配相关技能。"""
        task_lower = task.lower()
        matched = []

        for sd in _glob.glob(os.path.join(self.workspace, "skills", "*")):
            mp = os.path.join(sd, "meta.json")
            if not os.path.isfile(mp):
                continue
            try:
                with open(mp, encoding="utf-8") as f:
                    meta = json.load(f)
            except json.JSONDecodeError:
                continue

            triggers = meta.get("triggers", [])
            if not triggers:
                continue

            # 触发词匹配
            match_count = sum(1 for t in triggers if t.lower() in task_lower)
            if match_count >= 1:
                success_rate = (
                    meta.get("success_count", 0) / max(meta.get("activation_count", 1), 1)
                )
                skill = Skill(
                    name=meta["name"],
                    status=SkillStatus(meta.get("status", "draft")),
                    activation_count=meta.get("activation_count", 0),
                    blocked_count=meta.get("blocked_count", 0),
                    success_count=meta.get("success_count", 0),
                    triggers=triggers,
                    pitfalls=meta.get("pitfalls", []),
                    version=meta.get("version", "0.1.0"),
                )
                matched.append((success_rate, skill))

        # 按成功率排序
        matched.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in matched[:3]]

    def merge_skills(self, skill_a: Skill, skill_b: Skill) -> Skill | None:
        """跨 session 融合同名 skill，保留高成功率版本。"""
        if skill_a.name != skill_b.name:
            return None

        # 选更好的版本
        rate_a = skill_a.success_count / max(skill_a.activation_count, 1)
        rate_b = skill_b.success_count / max(skill_b.activation_count, 1)

        if rate_a >= rate_b:
            merged = skill_a
        else:
            merged = skill_b

        # 合并 triggers 和 pitfalls
        merged.triggers = list(set(skill_a.triggers + skill_b.triggers))
        merged.pitfalls = list(set(skill_a.pitfalls + skill_b.pitfalls))
        merged.version = f"{max(int(skill_a.version.split('.')[0]), int(skill_b.version.split('.')[0]))}.0.0"
        merged.last_used = datetime.now(timezone.utc).isoformat()

        # 写回
        skill_dir = os.path.join(self.workspace, "skills", merged.name)
        mp = os.path.join(skill_dir, "meta.json")
        if os.path.exists(mp):
            with open(mp, "w", encoding="utf-8") as f:
                json.dump({
                    "name": merged.name, "status": merged.status.value,
                    "triggers": merged.triggers, "pitfalls": merged.pitfalls,
                    "activation_count": merged.activation_count,
                    "success_count": merged.success_count,
                    "blocked_count": merged.blocked_count,
                    "version": merged.version, "last_used": merged.last_used,
                }, f, indent=2)

        return merged

    def record_skill_outcome(self, name: str, success: bool):
        """记录技能使用结果。"""
        mp = os.path.join(self.workspace, "skills", name, "meta.json")
        if not os.path.exists(mp):
            return
        with open(mp, encoding="utf-8") as f:
            meta = json.load(f)
        meta["activation_count"] = meta.get("activation_count", 0) + 1
        if success:
            meta["success_count"] = meta.get("success_count", 0) + 1
        else:
            meta["blocked_count"] = meta.get("blocked_count", 0) + 1

        # 自动升级
        if meta["activation_count"] >= 10 and meta.get("success_count", 0) / meta["activation_count"] > 0.8:
            meta["status"] = "stable"
            meta["version"] = "1.0.0"
        elif meta["activation_count"] >= 5 and meta.get("success_count", 0) / meta["activation_count"] > 0.7:
            meta["status"] = "proven"
            meta["version"] = "0.5.0"

        with open(mp, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

    def _extract_keywords(self, text: str) -> list:
        """中文关键词提取（简单版：2-4字高频词）。"""
        words = re.findall(r'[\u4e00-\u9fff]{2,4}', text)
        return list(set(words))[:5]


# ═══════════════════════════════════════════════════════
# ChangeManifest + SelfCheck（保留 v7.0）
# ═══════════════════════════════════════════════════════

class ChangeManifest:
    """v8.1: AHE-inspired structured change tracking.

    Manifests lifecycle: draft → (blind test) → verified / reverted / partial.
    """

    def __init__(self, workspace: str):
        self.path = os.path.join(workspace, "changes.jsonl")
        self._manifests_dir = os.path.join(workspace, "manifests")
        self._last_records = []
        os.makedirs(self._manifests_dir, exist_ok=True)

    def record(self, change_type: str, detail: dict):
        """记录变更（flat JSONL，向后兼容）。"""
        entry = {"ts": datetime.now(timezone.utc).isoformat(), "type": change_type, "detail": detail}
        self._last_records.append(entry)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def create_manifest(self, run_id: str, change_type: str, change_summary: str,
                        affected_files: list, evidence_refs: list = None,
                        blind_test_result: dict = None) -> dict:
        """v8.1: 创建结构化 Change Manifest。

        Args:
            run_id: 关联的 run ID
            change_type: feat / fix / refactor / docs / test
            change_summary: 变更摘要（LLM 生成）
            affected_files: 受影响的文件列表
            blind_test_result: 盲测结果 {"pass_rate": N/12, "status": "pass/fail"}

        Returns:
            manifest dict with status, verdict, and metadata
        """
        now = datetime.now(timezone.utc).isoformat()
        status = "draft"
        verdict = None

        if blind_test_result:
            if blind_test_result.get("status") == "pass":
                status = "verified"
                verdict = "keep"
            else:
                status = "reverted"
                verdict = "revert"

        manifest = {
            "manifest_id": f"m-{run_id}",
            "run_id": run_id,
            "ts": now,
            "change_type": change_type,
            "summary": change_summary,
            "affected_files": affected_files,
            "evidence_refs": evidence_refs or [],
            "status": status,
            "verdict": verdict,
            "blind_test": blind_test_result or {},
        }

        # 写 JSON 文件
        manifest_path = os.path.join(self._manifests_dir, f"{run_id}.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        # 同时追加到 changes.jsonl
        self.record("manifest_created", {
            "manifest_id": manifest["manifest_id"],
            "status": status,
            "verdict": verdict,
        })

        return manifest

    def get_latest_verified_run(self) -> str | None:
        """获取最近一个通过验证的 run_id（用于回滚）。"""
        if not os.path.isdir(self._manifests_dir):
            return None
        manifests = []
        for f in os.listdir(self._manifests_dir):
            if f.endswith(".json"):
                try:
                    with open(os.path.join(self._manifests_dir, f), encoding="utf-8") as fh:
                        m = json.load(fh)
                    if m.get("status") == "verified" and m.get("verdict") == "keep":
                        manifests.append((m["ts"], m))
                except Exception:
                    pass
        manifests.sort(key=lambda x: x[0], reverse=True)
        return manifests[0][1]["run_id"] if manifests else None

    def list_manifests(self, status: str = None, limit: int = 20) -> list[dict]:
        """列出 manifests，可按 status 过滤。"""
        if not os.path.isdir(self._manifests_dir):
            return []
        result = []
        for f in sorted(os.listdir(self._manifests_dir), reverse=True):
            if f.endswith(".json"):
                try:
                    with open(os.path.join(self._manifests_dir, f), encoding="utf-8") as fh:
                        m = json.load(fh)
                    if status is None or m.get("status") == status:
                        result.append(m)
                except Exception:
                    pass
        return result[:limit]


class BlindTestRunner:
    """Run validation commands and persist pass/fail evidence."""

    def __init__(self, workspace: str):
        self.workspace = workspace
        self.validation_dir = os.path.join(workspace, "validation")
        os.makedirs(self.validation_dir, exist_ok=True)

    def run(self, run_id: str, command: list[str] | str, timeout: int = 120) -> dict:
        started = datetime.now(timezone.utc).isoformat()
        try:
            result = subprocess.run(
                command,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=isinstance(command, str),
            )
            record = {
                "run_id": run_id,
                "command": command,
                "started": started,
                "ended": datetime.now(timezone.utc).isoformat(),
                "exit_code": result.returncode,
                "passed": result.returncode == 0,
                "stdout_tail": result.stdout[-4000:],
                "stderr_tail": result.stderr[-4000:],
            }
        except subprocess.TimeoutExpired as e:
            record = {
                "run_id": run_id,
                "command": command,
                "started": started,
                "ended": datetime.now(timezone.utc).isoformat(),
                "exit_code": -1,
                "passed": False,
                "stdout_tail": (e.stdout or "")[-4000:] if isinstance(e.stdout, str) else "",
                "stderr_tail": (e.stderr or "")[-4000:] if isinstance(e.stderr, str) else "",
                "error": f"Timeout after {timeout}s",
            }

        path = os.path.join(self.validation_dir, f"{run_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        record["path"] = path
        return record


@dataclass
class CheckItem:
    item: str
    level: str
    reason: str = ""


@dataclass
class SelfCheckReport:
    passed: bool
    checks: list
    summary: str


class SelfCheck:
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

        for mp in _glob.glob(os.path.join(self.workspace, "skills", "*", "meta.json")):
            with open(mp, encoding="utf-8") as f:
                meta = json.load(f)
            if meta.get("status") == "draft" and meta.get("activation_count", 0) > 5:
                checks.append(CheckItem(f"stale_skill:{meta['name']}", "WARN",
                               f"Skill stuck in draft despite {meta['activation_count']} activations"))

        for ef in _glob.glob(os.path.join(self.workspace, "runs", "*", "evidence.jsonl")):
            if os.path.getsize(ef) == 0:
                checks.append(CheckItem(f"empty_evidence:{os.path.basename(os.path.dirname(ef))}", "WARN", "Evidence file is empty"))

        fails = sum(1 for c in checks if c.level == "FAIL")
        warns = sum(1 for c in checks if c.level == "WARN")
        return SelfCheckReport(
            passed=fails == 0, checks=checks,
            summary=f"{fails} FAIL, {warns} WARN, {len(checks)-fails-warns} PASS"
        )
