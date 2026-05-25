# delegate.py — 子Agent委托 v8.0
"""监督者-工人（Supervisor-Worker）模式，支持并行任务执行。

设计原则（Cognition.ai「Don't Build Multi-Agents」）：
1. 共享完整上下文 — 子Agent看到父Agent的全部对话历史
2. 动作携带隐式决策 — 返回完整工具调用轨迹，不只是结果
"""

import json, os
from datetime import datetime, timezone
from dataclasses import dataclass, field


@dataclass
class DelegateResult:
    goal: str
    result: str                # 最终文本结果
    tool_traces: list          # [(tool_name, args, result), ...]
    steps: int
    status: str                # success / max_steps / error
    run_id: str
    error: str = ""


class SubAgent:
    """轻量子Agent，在同进程中运行独立的 ReAct 循环。

    与主 Agent 共享 ModelGateway 和 ToolRegistry，但有独立的上下文和步数限制。
    """

    def __init__(self, model, tool_registry, max_steps: int = 20):
        self.model = model
        self.tool_registry = tool_registry
        self.max_steps = max_steps

    def run(self, goal: str, parent_messages: list, parent_workspace: str) -> DelegateResult:
        """执行子任务。

        Args:
            goal: 子任务描述
            parent_messages: 父 Agent 的完整对话历史（共享上下文原则）
            parent_workspace: 父 Agent 的工作目录
        """
        run_id = "sub-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        messages = []

        # 共享父Agent上下文（原则1: Share context）
        sys_msg = (
            "[SubAgent] You are a worker agent. Your task is below.\n"
            "Complete it using the available tools. Be thorough.\n"
            "Return your final answer as plain text."
        )
        messages.append({"role": "system", "content": sys_msg})

        # 注入父Agent最近的上下文（最近20条消息）
        for m in parent_messages[-20:]:
            if m.get("role") in ("user", "assistant", "system", "tool"):
                messages.append(m)

        messages.append({"role": "user", "content": f"[TASK]\n{goal}\n\nComplete this task and report your results."})

        tool_traces = []
        tools_schema = self.tool_registry.get_schemas()

        for step in range(1, self.max_steps + 1):
            try:
                response = self.model.chat(messages=messages, tools=tools_schema)
            except Exception as e:
                return DelegateResult(
                    goal=goal, result="", tool_traces=tool_traces,
                    steps=step, status="error", run_id=run_id, error=str(e)
                )

            if "error" in response:
                return DelegateResult(
                    goal=goal, result="", tool_traces=tool_traces,
                    steps=step, status="error", run_id=run_id,
                    error=response["error"]
                )

            tool_calls = response.get("tool_calls", [])
            if not tool_calls and response.get("finish_reason", "") == "stop":
                result_text = response.get("content", "")
                messages.append({"role": "assistant", "content": result_text})
                return DelegateResult(
                    goal=goal, result=result_text, tool_traces=tool_traces,
                    steps=step, status="success", run_id=run_id
                )

            if not tool_calls:
                messages.append({"role": "assistant", "content": response.get("content", "")})
                continue

            # 执行工具调用
            assistant_msg = {"role": "assistant", "content": response.get("content") or ""}
            assistant_msg["tool_calls"] = tool_calls
            messages.append(assistant_msg)

            for tc in tool_calls:
                tn = tc.get("function", {}).get("name", "unknown")
                ta_str = tc.get("function", {}).get("arguments", "{}")
                tid = tc.get("id", "")

                try:
                    ta = json.loads(ta_str)
                except json.JSONDecodeError:
                    ta = {}

                try:
                    # 直接在父 workspace 执行（子Agent共享文件系统）
                    result = self.tool_registry.execute(tn, ta)
                    tool_traces.append((tn, ta, result))
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tid,
                        "content": json.dumps(result, ensure_ascii=False)
                    })
                except Exception as e:
                    tool_traces.append((tn, ta, {"error": str(e)}))
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tid,
                        "content": json.dumps({"error": str(e)}, ensure_ascii=False)
                    })

        # 达到最大步数
        return DelegateResult(
            goal=goal, result="Max steps reached", tool_traces=tool_traces,
            steps=self.max_steps, status="max_steps", run_id=run_id
        )
