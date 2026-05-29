# agent.py — YINYO Agent Loop v8.2（超时保护 + 空响应检测 + /stop 停止）
import os, json, time, uuid
from datetime import datetime, timezone

try:
    from .context import ContextManager
    from .evidence import EvidenceLedger, VerificationGate, RunManifest
    from .memory import MemoryStore
    from .model import ModelGateway, ThinkingMode
    from .governance import RiskPolicy, redact_secrets
    from .memory_tool import load_memory_context, ensure_memory_files
    from . import tools as tools_module
    from .tools import (
        registry as tool_registry,
        execute_tool_with_evidence,
        load_yaml_tools,
        set_memory_workspace,
        set_tool_workspace,
        set_parent_agent,
    )
    from .evolution import SkillCrystallizer, ChangeManifest, SelfCheck, SkillEvolution
    from .session import SessionManager
except ImportError:
    from context import ContextManager
    from evidence import EvidenceLedger, VerificationGate, RunManifest
    from memory import MemoryStore
    from model import ModelGateway, ThinkingMode
    from governance import RiskPolicy, redact_secrets
    from memory_tool import load_memory_context, ensure_memory_files
    import tools as tools_module
    from tools import (
        registry as tool_registry,
        execute_tool_with_evidence,
        load_yaml_tools,
        set_memory_workspace,
        set_tool_workspace,
        set_parent_agent,
    )
    from evolution import SkillCrystallizer, ChangeManifest, SelfCheck, SkillEvolution
    from session import SessionManager


class YinyoAgent:
    """YINYO v8.2 — 超时保护 + 空响应检测 + /stop 停止 + 双重去重修复。"""

    def __init__(self, workspace: str = ".", max_steps: int = 50,
                 thinking_mode: ThinkingMode = ThinkingMode.NON_THINK,
                 api_key: str = None, base_url: str = "https://api.deepseek.com",
                 default_model: str = "deepseek-v4-flash",
                 max_runtime_seconds: int = 300,
                 model_timeout_seconds: int = 120,
                 model_retry_count: int = 0,
                 model_retry_backoff_seconds: float = 0):
        self.workspace = os.path.abspath(workspace)
        self.max_steps = max_steps
        self.max_runtime_seconds = max_runtime_seconds  # v8.2: 超时保护
        os.makedirs(self.workspace, exist_ok=True)

        self.context = ContextManager(cache_dir=os.path.join(self.workspace, "cache"))
        self.memory = MemoryStore(self.workspace)
        self.model = ModelGateway(
            api_key=api_key,
            base_url=base_url,
            default_model=default_model,
            thinking=thinking_mode,
            timeout_seconds=model_timeout_seconds,
            retry_count=model_retry_count,
            retry_backoff_seconds=model_retry_backoff_seconds,
        )
        self.governance = RiskPolicy(self.workspace)
        self.verifier = VerificationGate()
        self.crystallizer = SkillCrystallizer(self.workspace)
        self.change_manifest = ChangeManifest(self.workspace)
        self.self_check = SelfCheck(self.workspace)
        self.session_manager = SessionManager()
        self.context.set_model(self.model)

        # v8.0: Trace2Skill 闭环
        self.skill_evolution = SkillEvolution(self.workspace, model=self.model)

        # v8.0: Dual-Process — LLM 事实提取器
        self.memory.set_model(self.model)

        # v8.0: 暴露 agent 实例供 delegate_task 工具访问
        self._tool_registry = tool_registry
        set_parent_agent(self)

        self.run_count = 0

        ensure_memory_files(self.workspace)
        set_tool_workspace(self.workspace)
        set_memory_workspace(self.workspace)

        self.current_run_id: str = ""
        self.current_step: int = 0
        self.tool_sequence: list = []
        self._last_tool_results: list = []
        self.blocked_steps: int = 0

        self._run_selfcheck()
        self._autoload_yaml_tools()

    def handle_message(self, user_id: str, chat_id: str, text: str,
                       already_deduped: bool = False,
                       correlation_id: str = "") -> dict | None:
        """处理一条用户消息。返回回复 dict 或 None（被去重/停止）。

        Args:
            already_deduped: 如果调用方已经做过去重（如飞书 adapter），设为 True。
        """
        session = self.session_manager.get_or_create(user_id, chat_id)
        cmd_result = self.session_manager.handle_command(text, session)
        if cmd_result:
            return cmd_result
        # v8.2: /stop 后不执行任何非命令消息，直到 /new
        if session.stopped:
            return None
        if not already_deduped and self.session_manager.is_duplicate(text, user_id):
            return None
        session.add_user_message(text)
        result = self.run(text, correlation_id=correlation_id)
        session.add_assistant_message(result)
        final_response = ""
        for msg in reversed(self.context.messages):
            if msg.get("role") == "assistant" and msg.get("content"):
                final_response = msg["content"]
                break
        if not final_response:
            final_response = "Done (" + str(result.get("steps", 0)) + " steps)."
        if result.get("status") == "source_required":
            final_response = (
                "I need a cited source before treating this answer as verified. "
                "Please provide a source, or ask me to verify it live."
            )
        elif result.get("status") in {"partial", "model_error", "max_steps_reached"}:
            final_response = self._user_visible_failure(result)
        return {"text": final_response, "files": [], "run_id": result.get("run_id", "")}

    def _run_selfcheck(self):
        report = self.self_check.run()
        self.change_manifest.record(
            "self_check_passed" if report.passed else "self_check_failed",
            {"summary": report.summary, "checks_count": len(report.checks)}
        )

    def _autoload_yaml_tools(self):
        import glob
        for yf in glob.glob(os.path.join(self.workspace, "skills", "*", "tools.yaml")):
            count = load_yaml_tools(yf, tool_registry)
            if count > 0:
                self.change_manifest.record("config_changed", {
                    "key": "yaml_tools_loaded", "file": yf, "tools_count": count
                })

    def run(self, task: str, correlation_id: str = "") -> dict:
        run_id = "r-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
        correlation_id = correlation_id or run_id
        self.current_run_id = run_id
        self.current_step = 0
        self.tool_sequence = []
        self._last_tool_results = []
        self.blocked_steps = 0
        self.context.messages = []
        self._model_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "estimated_cost_usd": 0.0, "calls": 0}
        model_errors: list[dict] = []
        consecutive_failures = 0

        run_dir = os.path.join(self.workspace, "runs", run_id)
        start_time = time.time()  # v8.2: 超时保护
        empty_response_count = 0  # v8.2: 空响应检测
        manifest = RunManifest(run_dir)
        manifest.create(run_id, task, correlation_id=correlation_id)
        evidence = EvidenceLedger(run_dir)

        # ── System Prompt ──
        core = self.memory.load_core()
        sys_prompt = core.get("SOUL.md", "")[:2000]
        tools_schema = tool_registry.get_schemas()

        # v6.0: inject USER/MEMORY/AGENTS
        mc = load_memory_context(self.workspace)
        if mc.get("user", "").strip():
            ub = "USER PROFILE [" + str(mc["user_chars"]) + "/" + str(mc["user_limit"]) + " chars]\n" + "=" * 50 + "\n" + mc["user"] + "\n"
            sys_prompt = ub + sys_prompt

        # v8.0: MEMORY.md 用 TemporalTree 摘要替代
        memory_summary = self.memory.get_memory_summary(max_chars=10000)
        if memory_summary:
            sys_prompt = "MEMORY [TemporalTree]\n" + "=" * 50 + "\n" + memory_summary + "\n" + sys_prompt

        for fn in ["AGENTS.md", ".yinyo.md"]:
            ap = os.path.join(self.workspace, fn)
            if os.path.isfile(ap):
                with open(ap, "r", encoding="utf-8") as f:
                    agents = f.read()[:1500]
                sys_prompt = "PROJECT CONTEXT (" + fn + ")\n" + agents + "\n" + sys_prompt
                break

        self.context.messages.append({"role": "system", "content": sys_prompt})
        self.context.messages.append({"role": "user", "content": task})

        # ── Memory Retrieval ──
        mem_msgs = self.context.retrieve_memory(self.memory, task, limit=3)
        for mm in mem_msgs:
            self.context.messages.append(mm)

        # v8.0: Auto-load skills
        skills = self.skill_evolution.auto_load_skills(task)
        loaded_skill_names = []
        if skills:
            skill_text = "\n".join(
                f"[SKILL: {s.name} v{s.version}] Triggers: {s.triggers}\nSteps: see skills/{s.name}/SKILL.md"
                for s in skills
            )
            self.context.messages.append({"role": "system", "content": f"Relevant skills loaded:\n{skill_text}"})
            loaded_skill_names = [s.name for s in skills]

        # ── Plan ──
        pp = "Before executing, create a concise step-by-step plan. Format: [STEP N] goal -> tool -> expected result. Be specific. Only output the plan."
        pm = list(self.context.messages) + [{"role": "user", "content": pp}]
        pr = self.model.chat(messages=pm, tools=None, thinking=ThinkingMode.THINK_HIGH, max_tokens=512)
        self._record_model_usage(pr)
        if "error" in pr:
            model_errors.append(self._model_error_summary(pr, step=0))
        pt = pr.get("content", "")
        if pt and "error" not in pr:
            self.context.messages.append({"role": "system", "content": "[Plan]\n" + pt + "\n\nExecute the plan step by step."})

        # ── ReAct Loop ──
        while self.current_step < self.max_steps:
            # v8.2: 超时保护
            if time.time() - start_time > self.max_runtime_seconds:
                raise TimeoutError(f"Agent runtime exceeded {self.max_runtime_seconds}s")
            self.current_step += 1
            self.context.auto_manage(self.current_step)

            thinking = self._resolve_thinking(consecutive_failures)
            response = self.model.chat(messages=self.context.messages, tools=tools_schema, thinking=thinking)
            self._record_model_usage(response)

            if response.get("_fallback"):
                self.change_manifest.record("config_changed", {
                    "key": "model_fallback",
                    "from": response.get("_fallback_from", "unknown"),
                    "to": response.get("model", "unknown"),
                })
                self.context.messages.append({"role": "system", "content": "[System: Model fallback]"})

            if "error" in response:
                error_summary = self._model_error_summary(response, step=self.current_step)
                model_errors.append(error_summary)
                self.change_manifest.record("model_error", error_summary)
                self.context.messages.append({"role": "user", "content": "[System: API error: " + error_summary["error"] + "]"})
                consecutive_failures += 1
                continue

            tool_calls = response.get("tool_calls", [])
            if not tool_calls and response.get("finish_reason", "") == "stop":
                ac = response.get("content", "")
                if ac:
                    self.context.messages.append({"role": "assistant", "content": ac})
                break

            # v8.2: 无工具调用且非 stop → 空响应检测（防死循环）
            if not tool_calls:
                empty_response_count += 1
                if empty_response_count > 3:
                    self.context.messages.append({"role": "user", "content": "[System: Too many empty responses. Stopping.]"})
                    break
                self.context.messages.append({"role": "assistant", "content": response.get("content", "")})
                continue

            am = {"role": "assistant", "content": response.get("content") or ""}
            if "reasoning_content" in response:
                am["reasoning_content"] = response["reasoning_content"]
            am["tool_calls"] = tool_calls
            self.context.messages.append(am)

            step_has_blocked = False
            for tc in tool_calls:
                tn = tc.get("function", {}).get("name", "unknown")
                ta_str = tc.get("function", {}).get("arguments", "{}")
                tid = tc.get("id", "")
                try:
                    ta = json.loads(ta_str)
                except json.JSONDecodeError:
                    ta = {}

                result = execute_tool_with_evidence(
                    tool_registry, tn, ta, evidence, self.governance,
                    run_id, self.current_step, correlation_id=correlation_id,
                )
                self._last_tool_results.append((tn, ta, result))
                verify = self.verifier.verify({"tool": tn, "args": ta, "result": result, "hash": result.get("hash", "")})

                if verify.status == "blocked":
                    self.blocked_steps += 1
                    step_has_blocked = True
                    manifest.update(blocked_reason=verify.reason)
                    self.context.messages.append({"role": "tool", "tool_call_id": tid, "content": json.dumps({"error": "Verification blocked: " + verify.reason, "_blocked": True}, ensure_ascii=False)})
                    continue

                self.tool_sequence.append(tn)
                self.context.messages.append({"role": "tool", "tool_call_id": tid, "content": json.dumps(result, ensure_ascii=False)})

            if step_has_blocked:
                consecutive_failures += 1
            else:
                consecutive_failures = 0
            if consecutive_failures >= 2:
                continue

        if model_errors and not self.tool_sequence and self.current_step >= self.max_steps:
            final_status = "model_error"
        elif self.blocked_steps > 0:
            final_status = "partial"
        else:
            final_status = "success" if self.current_step < self.max_steps else "max_steps_reached"
        final_answer = self._latest_assistant_text()
        source_audit = self._source_audit(task, final_answer)
        if final_status == "success" and source_audit["required"] and not source_audit["satisfied"]:
            final_status = "source_required"
            self.change_manifest.record("source_required", source_audit)
        manifest.update(status=final_status, steps=self.current_step, tools_used=list(set(self.tool_sequence)),
                        ended=datetime.now(timezone.utc).isoformat(),
                        correlation_id=correlation_id,
                        model_usage=self._model_usage,
                        model_errors=model_errors[-5:],
                        source_audit=source_audit,
                        verification={"verified_steps": self.current_step - self.blocked_steps, "blocked_steps": self.blocked_steps,
                                      "final_status": "verified" if self.blocked_steps == 0 and final_status == "success" else final_status})

        # ── Skill Crystallization ──
        skill = self.crystallizer.observe(self.tool_sequence)
        if skill:
            self.change_manifest.record("skill_crystallized", {"skill": skill.name, "tools": self.tool_sequence, "status": skill.status.value})

        # ── Auto-Reflect ──
        summary_text = "Task: " + task[:100] + ". Steps: " + str(self.current_step) + ". Tools: " + str(list(set(self.tool_sequence))) + ". Status: " + final_status + "."
        reflection = self._reflect_on_run(task, summary_text, run_id, run_dir)

        # v8.0: Dual-Process — LLM 事实提取 → 存入 TemporalTree
        memory_extract = self.memory.extract_and_store(self.context.messages, run_id)
        if memory_extract and memory_extract.get("rejected"):
            self.change_manifest.record("memory_fact_rejected", {
                "run_id": run_id,
                "rejected": memory_extract.get("rejected", 0),
                "reasons": memory_extract.get("reasons", [])[:5],
            })

        # v8.0: Trace2Skill — 检测失败模式
        if final_status != "success" or self.blocked_steps > 0:
            error_msg = f"Status: {final_status}, Blocked: {self.blocked_steps}"
            pattern = self.skill_evolution.detect_failure_pattern(task, error_msg, [])
            if pattern and pattern.occurrence_count >= 2:
                new_skill = self.skill_evolution.extract_skill_from_failure(
                    pattern, task, error_msg, self.context.messages
                )
                if new_skill:
                    self.change_manifest.record("skill_extracted_from_failure", {
                        "skill": new_skill.name, "pattern": pattern.task_keywords,
                    })

        # v8.0: 记录技能使用结果
        for sname in loaded_skill_names:
            self.skill_evolution.record_skill_outcome(sname, final_status == "success")

        # ── Episodic Save ──
        self.memory.save_episodic(run_id, [], summary_text)
        self.change_manifest.record("memory_updated", {"layer": "L2", "run_id": run_id, "summary": summary_text[:200]})
        self.memory.archive_shadow(run_id)

        # v7.0: Deep-Reflect
        self.run_count += 1
        if self.run_count % 10 == 0:
            self._deep_reflect()

        # v8.1: AHE-inspired — 自动生成 Change Manifest
        self._auto_manifest(run_id, task, summary_text, final_status)
        handoff = self._write_handoff_record(
            run_id=run_id,
            correlation_id=correlation_id,
            task=task,
            status=final_status,
            summary=summary_text,
            source_audit=source_audit,
            model_errors=model_errors[-5:],
        )
        manifest.update(model_usage=self._model_usage, handoff=handoff)

        fallback_events = []
        for line in getattr(self.change_manifest, "_last_records", []):
            if line.get("type") == "config_changed" and line.get("detail", {}).get("key") == "model_fallback":
                fallback_events.append(line["detail"])

        return {"run_id": run_id, "correlation_id": correlation_id, "status": final_status, "steps": self.current_step,
                "tools_used": list(set(self.tool_sequence)), "evidence_file": "runs/" + run_id + "/evidence.jsonl",
                "reflection": reflection, "fallbacks": fallback_events, "model_usage": self._model_usage,
                "model_errors": model_errors[-5:], "source_audit": source_audit,
                "handoff_file": handoff.get("path", "")}

    def _write_handoff_record(self, *, run_id: str, correlation_id: str, task: str,
                              status: str, summary: str, source_audit: dict,
                              model_errors: list[dict]) -> dict:
        """Persist a compact state-transfer packet for the next operator/agent."""
        run_dir = os.path.join(self.workspace, "runs", run_id)
        os.makedirs(run_dir, exist_ok=True)
        evidence_file = os.path.join(run_dir, "evidence.jsonl")
        if not os.path.exists(evidence_file):
            open(evidence_file, "a", encoding="utf-8").close()
        evidence_refs = []
        risk_notes = []
        unresolved = []
        if os.path.isfile(evidence_file):
            with open(evidence_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    evidence_refs.append(record.get("hash", ""))
                    preview = record.get("result", {}).get("preview", "")
                    if "_blocked" in preview or "Blocked" in preview:
                        risk_notes.append({
                            "tool": record.get("tool", ""),
                            "step": record.get("step", 0),
                            "preview": preview[:200],
                        })
        if status != "success":
            unresolved.append(f"run_status:{status}")
        if source_audit.get("required") and not source_audit.get("satisfied"):
            unresolved.append("source_required")
        if model_errors:
            unresolved.append("model_errors")
        budget_state = {
            "max_steps": self.max_steps,
            "steps_used": self.current_step,
            "steps_remaining": max(self.max_steps - self.current_step, 0),
            "max_runtime_seconds": self.max_runtime_seconds,
            "model_usage": self._model_usage,
        }
        trace_history = {
            "correlation_id": correlation_id,
            "evidence_hashes": [ref for ref in evidence_refs if ref],
            "tools_used": list(dict.fromkeys(self.tool_sequence)),
            "model_errors": model_errors[-5:],
        }

        payload = {
            "schema": "yinyo.handoff.v1",
            "run_id": run_id,
            "correlation_id": correlation_id,
            "task": task,
            "status": status,
            "summary": summary[:500],
            "intent": {
                "original_task": task,
                "final_status": status,
            },
            "constraints": {
                "workspace": self.workspace,
                "max_steps": self.max_steps,
                "max_runtime_seconds": self.max_runtime_seconds,
            },
            "permissions": {
                "confirm_tools_require_structured_metadata": True,
                "workspace_isolation": True,
            },
            "artifacts": {
                "evidence_file": "runs/" + run_id + "/evidence.jsonl",
                "manifest_file": "runs/" + run_id + "/manifest.json",
                "change_manifest_file": "manifests/" + run_id + ".json",
            },
            "provenance": {
                "tools_used": list(dict.fromkeys(self.tool_sequence)),
                "evidence_hashes": [ref for ref in evidence_refs if ref],
                "model_usage": self._model_usage,
                "source_audit": source_audit,
            },
            "budget_state": budget_state,
            "trace_history": trace_history,
            "risk": {
                "blocked_steps": self.blocked_steps,
                "risk_notes": risk_notes[-5:],
                "model_errors": model_errors[-5:],
            },
            "unresolved": unresolved,
        }
        handoff_path = os.path.join(run_dir, "handoff.json")
        with open(handoff_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return {
            "path": "runs/" + run_id + "/handoff.json",
            "schema": payload["schema"],
            "unresolved": unresolved,
        }

    def _model_error_summary(self, response: dict, *, step: int) -> dict:
        error = redact_secrets(str(response.get("error", "")))[:240]
        attempts = []
        for item in response.get("_attempts", []) or []:
            if not isinstance(item, dict):
                continue
            attempts.append({
                "provider": str(item.get("provider", "")),
                "model": str(item.get("model", "")),
                "attempt": item.get("attempt", ""),
                "ok": bool(item.get("ok")),
                "error": redact_secrets(str(item.get("error", "")))[:160],
            })
        return {
            "step": step,
            "error": error,
            "attempts": attempts[-5:],
        }

    def _user_visible_failure(self, result: dict) -> str:
        status = result.get("status", "partial")
        if status == "model_error":
            return (
                "I could not complete this because the model provider failed. "
                "No successful answer was verified; check the run evidence before retrying."
            )
        if status == "max_steps_reached":
            return (
                "I stopped before completing the task because the step limit was reached. "
                "Review the run evidence and continue with a narrower request."
            )
        blocked = int(result.get("steps", 0) or 0)
        return (
            f"I completed only part of this task. Status: partial; steps: {blocked}. "
            "Some action was blocked or unverified, so review the run evidence before using the result."
        )

    def _latest_assistant_text(self) -> str:
        for msg in reversed(self.context.messages):
            if msg.get("role") == "assistant" and msg.get("content"):
                return str(msg["content"])
        return ""

    def _source_audit(self, task: str, answer: str) -> dict:
        required = self._requires_external_source(task)
        satisfied = (not required) or self._has_source_citation(answer)
        return {
            "required": required,
            "satisfied": satisfied,
            "reason": "external_or_current_fact" if required else "",
        }

    def _requires_external_source(self, text: str) -> bool:
        lowered = text.lower()
        markers = (
            "latest", "current", "today", "recent", "news", "weather", "price",
            "stock", "who is", "what is the current", "as of",
            "最近", "今天", "新闻", "天气", "股价", "价格", "最新", "现在",
        )
        return any(marker in lowered for marker in markers)

    def _has_source_citation(self, text: str) -> bool:
        lowered = text.lower()
        return "http://" in lowered or "https://" in lowered or "[source:" in lowered or "来源：" in text or "来源:" in text

    def _record_model_usage(self, response: dict | None) -> None:
        if not isinstance(response, dict):
            return
        usage = response.get("usage") or {}
        if not usage:
            return
        prompt = int(usage.get("prompt_tokens", 0) or 0)
        completion = int(usage.get("completion_tokens", 0) or 0)
        total = int(usage.get("total_tokens", prompt + completion) or 0)
        self._model_usage["prompt_tokens"] += prompt
        self._model_usage["completion_tokens"] += completion
        self._model_usage["total_tokens"] += total
        self._model_usage["calls"] += 1
        self._model_usage["estimated_cost_usd"] = round(
            self._model_usage["estimated_cost_usd"] + self._estimate_model_cost(response.get("model", ""), prompt, completion),
            8,
        )

    def _estimate_model_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        model = model or self.model.default_model
        input_per_million = 0.27
        output_per_million = 1.10 if "pro" in model else 0.55
        return (prompt_tokens / 1_000_000) * input_per_million + (completion_tokens / 1_000_000) * output_per_million

    def _auto_manifest(self, run_id: str, task: str, summary: str, status: str):
        """v8.1: 每次 run 结束，LLM 自动生成轻量 Change Manifest。

        AHE 之神（变更可追溯、验证自动化）+ DeepSeek 之器（LLM 替代规则引擎）。
        成本：~$0.0003/run。
        """
        if status != "success":
            return

        # 检测受影响的文件
        file_tools = {"do_write", "do_edit", "do_patch"}
        affected = []
        evidence_refs = []
        tool_set = []
        for fn, args, result in getattr(self, '_last_tool_results', []):
            if fn not in file_tools or result.get("_blocked") or result.get("error"):
                continue
            tool_set.append(fn)
            for k in ("path", "file"):
                if k in args:
                    affected.append(args[k])
            if result.get("_evidence_ref"):
                evidence_refs.append(result["_evidence_ref"])

        if not affected:
            return

        # LLM 生成变更摘要
        prompt = (
            "Summarize this agent run as a one-line change manifest. "
            "Output ONLY a JSON object: {change_type: 'feat'|'fix'|'refactor'|'docs'|'test', "
            "summary: 'one sentence describing what changed'}\n\n"
            f"Task: {task[:150]}\n"
            f"Tools used: {tool_set}\n"
            f"Files: {affected[:5]}\n"
            f"Evidence refs: {evidence_refs[:5]}\n"
            f"Status: {status}"
        )
        try:
            resp = self.model.chat(
                messages=[{"role": "user", "content": prompt}],
                tools=None, max_tokens=200,
            )
            self._record_model_usage(resp)
            data = json.loads(resp.get("content", "{}"))
        except Exception:
            data = {"change_type": "feat", "summary": summary[:200]}

        # 创建 draft manifest（盲测通过后自动变为 verified）
        self.change_manifest.create_manifest(
            run_id=run_id,
            change_type=data.get("change_type", "feat"),
            change_summary=data.get("summary", summary[:200]),
            affected_files=list(set(affected)),
            evidence_refs=list(dict.fromkeys(evidence_refs)),
            blind_test_result=None,  # draft — 等盲测后更新
        )

    def verify_manifest(self, run_id: str, blind_test_pass: bool, pass_rate: str = ""):
        """v8.1: 盲测完成后，更新 manifest 状态。

        盲测通过 → verified/keep；失败 → reverted/revert。
        """
        manifest_path = os.path.join(self.workspace, "manifests", f"{run_id}.json")
        if not os.path.isfile(manifest_path):
            return

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        manifest["blind_test"] = {
            "status": "pass" if blind_test_pass else "fail",
            "pass_rate": pass_rate,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }

        if blind_test_pass:
            manifest["status"] = "verified"
            manifest["verdict"] = "keep"
        else:
            manifest["status"] = "reverted"
            manifest["verdict"] = "revert"

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        self.change_manifest.record("manifest_verified", {
            "run_id": run_id,
            "blind_test_pass": blind_test_pass,
            "verdict": manifest["verdict"],
        })

    def _reflect_on_run(self, task: str, summary: str, run_id: str, run_dir: str) -> str:
        """v7.0: LLM reflect after each run. v8.0: also feeds into TemporalTree via extract_and_store."""
        mp = os.path.join(self.workspace, "MEMORY.md")
        cm = ""
        if os.path.isfile(mp):
            with open(mp, "r", encoding="utf-8") as f:
                cm = f.read()[:2000]

        ep = os.path.join(run_dir, "evidence.jsonl")
        ev = ""
        if os.path.isfile(ep):
            with open(ep, "r", encoding="utf-8") as f:
                ls = f.readlines()[-5:]
                ev = "\n".join(l[:200] for l in ls)

        prompt = "Review this completed task and decide what to remember.\n\nTask: " + task + "\nResult: " + summary + "\nEvidence:\n" + ev + "\n\nCurrent MEMORY.md:\n" + cm + "\n\nOutput ONLY a JSON object with: reflections (list of 1-3 key lessons), memory_add (list of strings, empty if none), memory_update (list of {old_text, new_text}), memory_remove (list of strings)."
        try:
            resp = self.model.chat(messages=[{"role": "user", "content": prompt}], tools=None, max_tokens=500)
            self._record_model_usage(resp)
            raw_data = json.loads(resp.get("content", "{}"))
        except Exception:
            raw_data = {"reflections": [], "memory_add": [], "memory_update": [], "memory_remove": []}

        data, rejected = self._validate_reflection_payload(raw_data)
        if rejected:
            self.change_manifest.record("reflection_rejected", {
                "run_id": run_id,
                "rejected_count": rejected,
            })

        try:
            from .memory_tool import memory_add, memory_replace, memory_remove
        except ImportError:
            from memory_tool import memory_add, memory_replace, memory_remove
        for fact in data.get("memory_add", []):
            memory_add("memory", fact, self.workspace)
        for upd in data.get("memory_update", []):
            memory_replace("memory", upd.get("old_text", ""), upd.get("new_text", ""), self.workspace)
        for old in data.get("memory_remove", []):
            memory_remove("memory", old, self.workspace)

        rt = "\n".join("- " + r for r in data.get("reflections", []))
        if rt:
            rp = os.path.join(run_dir, "reflection.md")
            with open(rp, "w", encoding="utf-8") as f:
                f.write("# Run " + run_id + " Reflection\n\n" + rt + "\n")
            self.memory.vector_cache.add(run_id, rt, {"task": task[:100], "scope": "session"})
        return rt

    def _validate_reflection_payload(self, data: dict) -> tuple[dict, int]:
        """Validate LLM reflection output before it mutates memory files."""
        rejected = 0
        if not isinstance(data, dict):
            return {"reflections": [], "memory_add": [], "memory_update": [], "memory_remove": []}, 1

        def clean_string_list(value, max_items=3, max_len=500):
            nonlocal rejected
            if not isinstance(value, list):
                if value not in (None, ""):
                    rejected += 1
                return []
            result = []
            for item in value:
                if not isinstance(item, str):
                    rejected += 1
                    continue
                text = item.strip()
                if not text or len(text) > max_len:
                    rejected += 1
                    continue
                result.append(text)
                if len(result) >= max_items:
                    break
            rejected += max(0, len(value) - len(result))
            return result

        updates = []
        raw_updates = data.get("memory_update", [])
        if isinstance(raw_updates, list):
            for item in raw_updates:
                if not isinstance(item, dict):
                    rejected += 1
                    continue
                old_text = str(item.get("old_text", "")).strip()
                new_text = str(item.get("new_text", "")).strip()
                if not old_text or not new_text or len(old_text) > 500 or len(new_text) > 500:
                    rejected += 1
                    continue
                updates.append({"old_text": old_text, "new_text": new_text})
                if len(updates) >= 3:
                    break
            rejected += max(0, len(raw_updates) - len(updates))
        elif raw_updates not in (None, ""):
            rejected += 1

        return {
            "reflections": clean_string_list(data.get("reflections", []), max_items=3, max_len=500),
            "memory_add": clean_string_list(data.get("memory_add", []), max_items=3, max_len=500),
            "memory_update": updates,
            "memory_remove": clean_string_list(data.get("memory_remove", []), max_items=3, max_len=500),
        }, rejected

    def _deep_reflect(self):
        """v7.0: Periodic deep reflect. v8.0: adds pattern analysis to TemporalTree."""
        rd = os.path.join(self.workspace, "runs")
        if not os.path.isdir(rd):
            return
        recent = []
        for rid in sorted(os.listdir(rd), reverse=True)[:10]:
            rp = os.path.join(rd, rid, "reflection.md")
            if os.path.isfile(rp):
                with open(rp, "r", encoding="utf-8") as f:
                    recent.append("[" + rid + "] " + f.read()[:300])
        if len(recent) < 3:
            return

        mp = os.path.join(self.workspace, "MEMORY.md")
        cm = ""
        if os.path.isfile(mp):
            with open(mp, "r", encoding="utf-8") as f:
                cm = f.read()[:2000]

        prompt = "Analyze recent session reflections for patterns.\n\n" + "\n".join(recent) + "\n\nCurrent MEMORY.md:\n" + cm + "\n\nOutput ONLY JSON with: patterns, anti_patterns, user_trends, memory_updates (all lists of strings)."
        try:
            resp = self.model.chat(messages=[{"role": "user", "content": prompt}], tools=None, max_tokens=500)
            data = json.loads(resp.get("content", "{}"))
        except Exception:
            return

        try:
            from .memory_tool import memory_add
        except ImportError:
            from memory_tool import memory_add
        for fact in data.get("memory_updates", []):
            memory_add("memory", fact, self.workspace)
        for ap in data.get("anti_patterns", []):
            memory_add("memory", "[ANTI-PATTERN] " + ap, self.workspace)
            # ★ v8.0: anti-pattern 也存入 TemporalTree
            self.memory.add_fact(
                content=ap, category="Anti-Patterns",
                scopes={"type": "anti_pattern"},
                confidence=0.9, source_run_id="deep-reflect",
            )
        self.change_manifest.record("deep_reflect", {"patterns": len(data.get("patterns", [])), "anti_patterns": len(data.get("anti_patterns", []))})

    def _resolve_thinking(self, consecutive_failures: int) -> ThinkingMode:
        if consecutive_failures >= 2:
            return ThinkingMode.THINK_MAX
        if consecutive_failures >= 1:
            return ThinkingMode.THINK_HIGH
        return self.model.thinking
