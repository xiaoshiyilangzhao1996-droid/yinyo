YINYO Harness Agent v2.0 架构设计 Spec
YINYO Harness Agent — 架构完整 Spec v2.0
**纲领：** Less is more。集百家之长。以证据为锚。
**定位：** 一个 compact DeepSeek-first Harness Agent runtime。
**范围：** 核心运行时 ~700 行 Python。总计 ~1,100 行（含 evidence/schema/adr/sandbox）。
**融合来源：** 隐曜 v1 Spec + 大管家 Spec + OpenClaw Spec，三方比对后重新整合。
**版本：** v2.1 | **日期：** 2026-05-24
**更新：** 基于 Hermes 修复全记录，重构 Context Management + 修正 agentmemory，新增三层记忆隔离原则
目录
[终局判词](#1-终局判词)
[设计原则与边界](#2-设计原则与边界)
[架构总览](#3-架构总览)
[组件规范](#4-组件规范)
[架构决策记录 (ADR)](#5-架构决策记录-adr)
[Phase Plan](#6-phase-plan)
[验收标准](#7-验收标准)
[附录](#8-附录)
1. 终局判词
**YINYO Harness Agent** 是一个 compact DeepSeek-first Harness Agent runtime。
它不是普通 Skill，也不是另一个 OpenClaw / Hermes，而是一个轻量 Agent harness runtime：
用极简 Agent Loop 管理任务
用 typed components 管理工具、记忆、上下文、证据和变更
用 **evidence ledger + verification gate** 约束模型幻觉
用 **manifest / ADR / memory schema** 把经验沉淀成可演化资产
**DeepSeek-first**，但不静默 fallback
**less is more**，不做大平台
1.1 核心差异化
能力 | smolagents | OpenHarness | Hermes/OpenClaw | **YINYO v2**
Code Agent | ✅ | ❌ | ❌ | ✅ **默认模式**
分层 Thinking | ❌ | ❌ | ❌ | ✅ **Non-think → High → Max**
Evidence Ledger | ❌ | ❌ | ❌ | ✅ **JSONL append-only**
Verification Gate | ❌ | ❌ | ❌ | ✅ **成功必须验证**
技能自结晶 | ❌ | ❌ | ❌ | ✅ **3次→Skill**
记忆分层 | ❌ AgentMemory | ✅ auto-compaction | ✅ File+SQLite | ✅ **5层 + Observation Masking**
DeepSeek 优化 | 通用 | 通用 | 适配 | ✅ **Context Caching + 分层模型**
代码量 | ~1200 | >5000 | >50000 | **< 800 核心 + 400 evidence**
2. 设计原则与边界

2.0 Context Management 核心原则（★ v2.1 新增，来自 Hermes 两天修复教训）

**教训来源：** Hermes Compressor 失败时暴力删除 136 条消息 → 上下文全白。
详见 `Hermes修复全记录.md` §四·根因①。

核心铁律（三条）：

```
铁律 1: 压缩失败 = 原样保留，绝不丢消息
铁律 2: 同 session 对话不自发跨 session 检索
铁律 3: 辅助调用的 provider 写死，不用 auto 探测
```

**为什么是这三条：** 三条合在一起才致命——DB 锁 → compressor 读不到历史 → 总结失败 → 删 136 条消息。拆开任何一条都不会出事。这三条铁律保证了"即使两条断了，第三条也能拦住"。

**与 LCM 的对齐：** Hermes LCM 的 DAG 无损归档思路值得吸收——消息 → 摘要 DAG 节点，原始消息可通过 grep/expand 钻取。YINYO 的 L1 上下文管理采用相同哲学：保留原消息 + 摘要，不删除。

2.1 核心原则（6 条）
# | 原则 | 含义
1 | **能力进化，而非预设** | 系统不预设任何技能。能力通过工具 + 记忆 → 技能结晶获得。
2 | **信息密度最大化** | 每行代码承载一个概念。Agent Loop ≤ 200 行。
3 | **证据即真相** | Agent 自报"完成"不等于完成。每个 tool action 有 evidence ref，verification 失败不能标 success。
4 | **Code Agent 优于 ReAct** | 让模型写代码来串联工具，步骤减少 30%，出错率更低。
5 | **自述能力 = 核心功能** | Agent 必须能阅读自己的内存、分析自己的技能、报告自己的状态。
6 | **三层记忆隔离** | L1(session) ≠ L2(cross-session) ≠ L3(persistent)，职责绝不混用。同 session 对话不自发检索其他 session（session_search 只响应用户显式命令）；跨 session 知识走 Memory（YINYO.md + SOUL.md 自动注入）；压缩失败不丢数据（原样保留）。三层各司其职，边界由 §4.2.3 的 should_search_sessions() 和 §4.2.2 的 compress() 安全降级强制执行。
2.2 Less is More 的约定
不加抽象层。不封装重试、不写基类工厂、不做事件总线。
工具即函数。`@tool` 装饰器 + 类型注解 = 全部工具定义。
Agent 即 Dict。所有状态平铺在对象属性上。
让模型做模型该做的事。不自己写 NER、不维护嵌入索引。

**关于 Evidence Engine 的说明：** Evidence Engine（§4.3）不是抽象层——它不封装重试、不写基类工厂、不做事件总线。它做的是具体功能：JSONL 追加写入 + 文件 hash 校验 + Manifest 生成。200 行中的绝大部分是格式定义和校验逻辑，没有抽象包装。
2.3 YINYO 不做的事
❌ 不做 | 原因
多 agent 编排 / 团队协作 | 不是 YINYO 的定位；那是框架层的事
插件市场 / 生态系统 | 极简优先，能力通过技能结晶获得
可视化 UI | 专注 headless runtime
重型沙箱（Docker/E2B/VM） | YINYO 用 SimpleExec（语法级安全拦截，~40 行），不做容器级隔离；用户如需容器沙箱可自行集成
MCP 原生集成 | 通过 tool adapter 间接接入
Agent 持久化管理 | 通过 agentmemory 集成（48k+ stars）
自动修改 provider / API key / config | 高风险，block by default
自动删除 / 推送 / 对外发布 | 高风险，block by default
同 session 对话中去翻别的 session 历史 | 跨 session 检索必须用户显式触发（说"查历史"/"之前聊过"）；不自发检索
辅助 provider 用 auto 模式探测 | 写死具体 provider（如 deepseek），不依赖 auto 探测不存在的通道
3. 架构总览
┌──────────────────────────────────────────────────────────┐
│  YINYO Harness Agent v2.0  (~800 行核心 + 400 evidence)  │
│                                                           │
│  Agent Loop       [~200 行]  ← Code Agent (default)      │
│    · plan → act → observe → verify → persist              │
│    · JSON tool-calling fallback                           │
│    · SimpleExec sandbox (语法级安全)                       │
│                                                           │
│  Context Manager  [~150 行]  ← Observation Masking 优先   │
│    · 三层自动升降：tool-result clearing → compaction      │
│      → memory retrieval                                   │
│    · JetBrains 2025 验证：Masking 比 LLM Summary          │
│      好 2.6%、便宜 52%                                    │
│    · DeepSeek 1M context 感知                              │
│                                                           │
│  Evidence Engine  [~200 行]  ★ 新增，吸收 OpenClaw 设计  │
│    · Evidence Ledger：JSONL append-only                   │
│    · Verification Gate：成功必须通过验证                   │
│    · Run Manifest：schema-valid JSON per run               │
│    · Secret redaction：manifest/log 不落密钥               │
│                                                           │
│  Memory Store     [~100 行 + agentmemory]                 │
│    · 5 层：Core → Episodic → Skill → Cache → Shadow       │
│    · agentmemory 集成（已有 OpenClaw 适配）                │
│    · SimpleMem 压缩（信息熵过滤）                          │
│                                                           │
│  Model Gateway    [~150 行]  ← DeepSeek 原生优化          │
│    · 主力：V4-Flash（284B/13B active）                    │
│    · 增强：V4-Pro（1.6T/49B active）                      │
│    · 分层 Thinking：Non-think / Think High / Think Max     │
│    · Context Caching：cache hit ~1/280 成本                │
│    · Fallback 链（不静默）                                 │
│                                                           │
│  Governance       [~100 行]  ★ 新增                      │
│    · Risk policy：高风险动作 gate + block by default      │
│    · Secret scan：log/manifest 写入前扫描                   │
│    · Permission levels：ALLOW / CONFIRM / BLOCK            │
│    · Provider/config mutation：blocked by default          │
│                                                           │
│  Evolution        [~80 行]                                │
│    · 技能结晶（3 次 → draft → proven → stable）           │
│    · Change Manifest（agent 自省基础）                     │
│    · Self-check（启动时自检 + 按需诊断）                   │
└──────────────────────────────────────────────────────────┘
3.1 行数预算
yinyo/
├── __init__.py              ←  10 行
├── agent.py                 ← 200 行  (Agent Loop)
├── context.py               ← 200 行  (Context Manager + DAG + 安全降级)
├── evidence.py              ← 200 行  (Evidence Ledger + Verification + Manifest)
├── memory.py                ← 100 行  (5 层记忆 + SimpleMem + agentmemory)
├── model.py                 ← 150 行  (模型调用 + Thinking + Caching)
├── governance.py            ← 100 行  (Risk + Secret + Permissions)
├── tools.py                 ←  80 行  (5 原子工具 + @tool 注册)
├── evolution.py             ←  80 行  (技能结晶 + Manifest + Self-check)
├── sandbox.py               ←  40 行  (SimpleExec)

SimpleExec 拦截清单：
- 危险 import：os.system, subprocess.Popen(shell=True), shutil.rmtree, eval, exec, compile
- 危险调用：__import__('os').system, getattr(os, 'system')
- 网络绑定：socket.bind, http.server（禁止开端口）
- 文件操作：os.remove/Path.unlink 在 workspace 外 → CONFIRM

─────────────                        ────
总计                         ~1,100 行  (兼容完整错误处理 + 类型注解)
核心逻辑（agent + context + evidence + model）≈ 700 行。
其余 ~410 行为 governance、tools、memory、evolution、sandbox——这些属于"执行支持层"，
代码依赖少、模块边界清晰，可独立开发和测试。
4. 组件规范

4.0 Tools — 原子工具系统

**设计原则：** 工具即函数。`@tool` 装饰器 + 类型注解 = 全部工具定义。不写基类工厂。

4.0.1 @tool 装饰器

```python
from typing import Callable, get_type_hints
import inspect

class Tool:
    """工具注册项。"""
    def __init__(self, name: str, fn: Callable, schema: dict, permission: str):
        self.name = name
        self.fn = fn
        self.schema = schema       # JSON Schema for model
        self.permission = permission  # ALLOW / CONFIRM / BLOCK

class ToolRegistry:
    """工具注册表。5 个原子工具 + 用户自定义 YAML 工具。"""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool):
        self._tools[tool.name] = tool

    def get_schemas(self) -> list[dict]:
        """返回所有工具的 JSON Schema 列表，注入 system prompt。"""
        return [t.schema for t in self._tools.values()]

    def dispatch(self, name: str, args: dict) -> dict:
        """按名称调度工具。"""
        tool = self._tools.get(name)
        if not tool:
            return {"error": f"Unknown tool: {name}"}
        return tool.fn(**args)


def tool(permission: str = "ALLOW"):
    """@tool 装饰器：把普通函数注册为 Agent 工具。

    用法：
        @tool(permission="CONFIRM")
        def do_write(path: str, content: str) -> dict: ...
    """
    def decorator(fn: Callable) -> Callable:
        hints = get_type_hints(fn)
        schema = _build_json_schema(fn.__name__, fn.__doc__ or "", hints)
        fn._tool_meta = {
            "name": fn.__name__,
            "schema": schema,
            "permission": permission,
        }
        return fn
    return decorator


def _build_json_schema(name: str, doc: str, hints: dict) -> dict:
    """从函数签名自动生成 JSON Schema（简化版）。"""
    type_map = {str: "string", int: "integer", float: "number", bool: "boolean", dict: "object", list: "array"}
    properties = {}
    required = []
    for param_name, param_type in hints.items():
        if param_name == "return": continue
        json_type = type_map.get(param_type, "string")
        properties[param_name] = {"type": json_type}
        required.append(param_name)
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": doc.strip().split("\n")[0] if doc else "",
            "parameters": {"type": "object", "properties": properties, "required": required},
        }
    }
```

4.0.2 用户自定义 YAML 工具

```yaml
# skills/fix-python-version/tools.yaml
tools:
  - name: do_check_python
    permission: ALLOW
    description: "Check Python version in a file"
    command: "grep -n 'python' {path}"
    parameters:
      path: {type: string, required: true}
```

YAML 工具在 Agent 启动时加载，通过 `ToolRegistry` 注册。YAML 工具一律走 `do_run` 执行，
受 SimpleExec 拦截清单约束。

4.0.3 工具输出到 Evidence 的回传路径

每个工具调用后，结果不直接注入 context，而是先走 Evidence Engine：

```python
def _execute_tool(self, name: str, args: dict) -> dict:
    tool = self.registry.dispatch(name, args)
    result = tool(**args)

    # 1. 写入 Evidence Ledger
    evidence_ref = self.evidence.record(
        run_id=self.current_run.id,
        step=self.current_run.step,
        tool=name,
        args=args,
        result=result,
    )

    # 2. 安全检查（Secret 扫描）
    if self.governance:
        result = self.governance.scan_and_redact(result)

    # 3. 回传给 Agent Loop（带 evidence ref）
    return {**result, "_evidence_ref": evidence_ref}
```

**关键规则：** 工具输出的 `_evidence_ref` 使 Agent Loop 的 VERIFY 阶段能定位证据来源。没有 evidence ref 的工具调用 = 不可验证 = 不能标 success。

4.0.4 内置工具注册示例

```python
# tools.py — 5 个原子工具
registry = ToolRegistry()

@tool(permission="ALLOW")
def do_read(path: str, offset: int = 1, limit: int = 500) -> dict:
    """Read a file with line numbers. Returns content and total lines."""
    ...

@tool(permission="CONFIRM")
def do_write(path: str, content: str, append: bool = False) -> dict:
    """Write content to a file. Returns bytes written and sha256 hash."""
    ...

# ... do_search, do_run, do_ask
for fn in [do_read, do_write, do_search, do_run, do_ask]:
    registry.register(Tool(**fn._tool_meta, fn=fn))
```


4.1 Agent Loop
**默认模式：Code Agent（借鉴 Smolagents）**
用户输入
    │
    ▼
┌─────────────┐
│  PLAN       │  模型分析任务 → 确定步骤
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  ACT        │  模型生成代码块 (```python ... ```)
│             │  代码中调用 tool_xxx() 函数
│             │  SimpleExec 执行
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  OBSERVE    │  收集工具返回结果
│             │  注入代码执行环境
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  VERIFY     │  ★ 必须通过验证
│             │  验证失败 → 回到 PLAN
│             │  验证通过 → 继续
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  PERSIST    │  写入 Evidence Ledger
│             │  更新 Run Manifest
│             │  Memory digest
└─────────────┘
**备选模式：JSON Tool-Calling**
当模型不支持 Code Agent 或用户指定时回退。
**Agent Loop 伪代码：**

```python
class YinyoAgent:
    def run(self, task: str) -> RunResult:
        run = self._init_run(task)
        
        while run.step < self.max_steps:
            # 1. PLAN: 模型分析当前状态
            plan = self.model.plan(task, self.context.get_messages(), run.get_progress())
            
            # 2. ACT: 生成并执行代码
            code = self.model.generate_code(plan)
            result = self.sandbox.execute(code, self.tools)
            
            # 3. OBSERVE: 收集工具输出
            observation = self._collect_observations(result)
            
            # 4. VERIFY: 验证执行结果
            verify = self.verifier.verify(result)
            if verify.status == "blocked":
                run.add_blocked_step(verify.reason)
                continue  # 回到 PLAN
            
            # 5. PERSIST: 写入证据
            self.evidence.record(run.id, run.step, result)
            self.context.add(observation)
            run.advance()
            
            if self._task_complete(plan, result):
                break
        
        return self._finalize(run)
```

**关键设计：**
- `self.sandbox.execute()` — SimpleExec 语法级安全拦截（见 §4.1.1）
- `self.verifier.verify()` — 验证失败 → 回到 PLAN，不吞错误
- 最多 50 步，防止无限循环



4.1.1 SimpleExec — 语法级安全沙箱（40 行）

**设计动机：** Code Agent 默认模式让模型写代码串联工具，需要一个轻量沙箱防止危险操作。
不做 Docker/E2B/VM 级别的容器隔离——那是用户自选的事。SimpleExec 只做语法级拦截。

**执行机制：**

SimpleExec 使用受限的 `exec()` 执行模型生成的代码，注入工具函数和白名单内置函数。

```python
import builtins

class SimpleExec:
    """语法级安全沙箱。拦截危险操作，注入工具函数。"""

    # 白名单内置函数（只允许安全的）
    ALLOWED_BUILTINS = {
        'print', 'len', 'range', 'enumerate', 'zip', 'map', 'filter',
        'sorted', 'reversed', 'min', 'max', 'sum', 'abs', 'round',
        'int', 'float', 'str', 'bool', 'list', 'dict', 'set', 'tuple',
        'type', 'isinstance', 'hasattr', 'getattr', 'setattr',
        'True', 'False', 'None', 'Exception', 'ValueError', 'TypeError',
    }

    # 拦截清单
    BLOCKED_IMPORTS = {
        'os', 'subprocess', 'shutil', 'sys', 'socket', 'ctypes',
        'importlib', 'pickle', 'marshal', 'code', 'codeop',
    }
    BLOCKED_CALLS = {
        'eval', 'exec', 'compile', '__import__', 'open',
        'breakpoint', 'input',
    }
    # 文件操作限制
    BLOCKED_FILE_OPS = {
        'os.remove', 'os.unlink', 'os.rmdir', 'shutil.rmtree',
        'Path.unlink', 'Path.rmdir',
    }

    def execute(self, code: str, tools: ToolRegistry) -> ExecResult:
        """执行模型生成的代码，注入工具函数。

        Args:
            code: 模型生成的 Python 代码（```python ... ``` 块内容）
            tools: 已注册的工具注册表

        Returns:
            ExecResult(output, errors, tool_calls)
        """
        # 1. 语法扫描（执行前拦截）
        scan_result = self._scan(code)
        if scan_result.blocked:
            return ExecResult(output="", errors=[scan_result.reason],
                            tool_calls=[], exit_code=1)

        # 2. 构建受限执行环境
        exec_globals = {
            '__builtins__': self._restricted_builtins(),
        }
        # 注入工具函数
        for tool in tools.list():
            exec_globals[tool.name] = tool.fn

        # 3. 执行
        output = io.StringIO()
        errors = []
        tool_calls = []

        try:
            with contextlib.redirect_stdout(output):
                exec(code, exec_globals)
        except Exception as e:
            errors.append(f"{type(e).__name__}: {e}")
            return ExecResult(output=output.getvalue(), errors=errors,
                            tool_calls=tool_calls, exit_code=1)

        return ExecResult(output=output.getvalue(), errors=errors,
                        tool_calls=tool_calls, exit_code=0)

    def _scan(self, code: str) -> ScanResult:
        """语法扫描：拦截危险 import / call / 文件操作。"""
        import ast

        tree = ast.parse(code)
        for node in ast.walk(tree):
            # 拦截危险 import
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split('.')[0] in self.BLOCKED_IMPORTS:
                        return ScanResult(blocked=True,
                            reason=f"Blocked import: {alias.name}")
            if isinstance(node, ast.ImportFrom):
                if node.module and node.module.split('.')[0] in self.BLOCKED_IMPORTS:
                    return ScanResult(blocked=True,
                        reason=f"Blocked import from: {node.module}")

            # 拦截危险调用
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in self.BLOCKED_CALLS:
                        return ScanResult(blocked=True,
                            reason=f"Blocked function call: {node.func.id}()")
        return ScanResult(blocked=False, reason="")

    def _restricted_builtins(self) -> dict:
        """只返回白名单中的内置函数。"""
        return {k: getattr(builtins, k) for k in self.ALLOWED_BUILTINS
                if hasattr(builtins, k)}
```

**拦截后行为：**
- `_scan()` 检测到危险代码 → 返回 `ExecResult(errors=["Blocked import: os"])`，不执行任何代码
- 不抛异常、不静默吞掉 → Agent Loop 收到 `exit_code=1`，触发 VERIFY → blocked → PLAN 重试
- 拦截原因写入 Evidence Ledger（通过 `tool_calls` 为空、`errors` 非空）

**不拦截但记录的行为：**
- `do_write` 在 workspace 外写文件 → CONFIRM（由 Governance 层 gate，不在 SimpleExec 层）
- `do_run` 的危险命令 → CONFIRM（由 Governance 层 gate）
- 网络请求 → 不拦截（模型可能需要调外部 API），由 Governance 的 HTTP POST/PUT/DELETE CONFIRM 机制覆盖


**内置工具（5 个）：**
工具 | 函数名 | 权限 | 说明
读 | `do_read(path, offset, limit)` | ALLOW | 文件读取，拦截敏感文件
写 | `do_write(path, content, append)` | CONFIRM | 文件写入，拦截系统目录
搜 | `do_search(query, path, file_glob, mode)` | ALLOW | 内容/文件名搜索
行 | `do_run(command, timeout, workdir)` | CONFIRM | Shell 执行，拦截危险命令
问 | `do_ask(question, model, context)` | ALLOW | 向另一模型查阅
4.2 Context Manager — 三层自动升降 + DAG 无损归档（★ v2.1 重写）

**设计哲学：** Context 是第一公民。压缩失败不能丢消息。跨 session 检索不能污染当前 session。

**核心反直觉发现（JetBrains 2025）：**
Observation Masking（保留最近 N 个工具结果 + 替换旧的）在 SWE-bench Verified 上比 LLM Summarization 解率高 2.6%、成本低 52%。

4.2.1 混合策略（三层自动升降）

Layer 1: Observation Masking       (成本: 零推理，效果 +2.6%)
  ├── 条件: token > 50% 预算
  ├── 动作: 保留最近 N 个工具输出，旧结果丢弃
  └── 验证: JetBrains 2025 实验证据

Layer 2: DAG Summarization         (成本: 有推理，无损)
  ├── 条件: token > 75% 预算
  ├── 动作: LLM 压缩 → 摘要 DAG 节点（LCM 风格）
  │         原始消息保留在 lcm.db，可通过 grep/expand 钻取
  └── 效果: 保留语义 + 原始消息可追溯

Layer 3: Memory Retrieval          (成本: 零推理)
  ├── 条件: session 边界
  ├── 动作: 写入 episodic → 下次任务通过 memory.adapt() 加载
  └── 效果: 跨 session 延续

4.2.2 安全降级规则（★ 来自 Hermes 修复全记录）

这是 v2.1 最重要的规则，直接来自 Hermes 丢 136 条消息的血训：

```python
def compress(self, messages: list, max_tokens: int) -> list:
    """压缩失败 = 原样返回，绝不丢消息"""
    if len(messages) < self.keep_tail:
        return messages  # 太少，不压缩

    try:
        summary = self._generate_summary(messages[:-self.keep_tail])
        if not summary:
            # ✅ 关键：失败时原样返回
            logger.warning("Summary generation failed -- skipping compression")
            return messages
        # 写入 DAG 节点（存储在 `cache/lcm.db`）+ 保留原始消息引用
        self._write_dag_node(summary, messages[:-self.keep_tail])
        return [summary] + messages[-self.keep_tail:]
    except Exception:
        # ✅ 任何异常都保留原消息
        logger.error(f"Compression crashed: {e}")
        return messages
```

**配置约束：**
- 压缩触发阈值：75%（非 50%，减少压缩频率）
- 保留尾部：最少 64 条消息不压缩
- 辅助 provider：**写死**为 DeepSeek，不走 auto 探测
- 不依赖 state.db 读取当前 session 消息

4.2.3 跨 Session 检索约束（★ 来自修复全记录 §二·问题一）

session_search 工具存在，但触发条件严格约束：

```python
def should_search_sessions(self, user_msg: str, context: list) -> bool:
    # Rule 1: explicit trigger words
    triggers = ["上次", "之前", "历史", "记得", "聊过", "查一下",
                "那个 bug", "那个文件", "怎么修的"]
    if not any(t in user_msg for t in triggers):
        return False

    # Rule 2: check if answerable from current context
    if self._answerable_from_context(user_msg, context):
        return False

    return True
```

**规则：** 同 session 对话不自发跨 session 检索。用户说"查历史" → 用；不说的 → 不用。不猜测用户意图。

4.2.4 Context Budget Allocator

| 预算项 | Token 数 | 说明 |
|--------|---------|------|
| 系统 Prompt（SOUL + USER + 工具定义） | ~4K | 固定前缀，可做 Context Caching |
| 最近 N 轮完整保留 | ~8K | 最近 3-5 轮完整对话 |
| DAG 摘要节点 | ~3K | 5-10 轮前的压缩摘要（可钻取） |
| L1 CORE 注入 | ~2K | YINYO.md + SOUL.md 核心 facts |
| 工具输出预留 | ~8K | 给文件读写/搜索等工具的输出 |
| **总预算** | **~25K** | 远低于 DeepSeek V4 128K 上限 |

4.3 Evidence Engine ★ 核心新增
**设计动机：** Agent 自报"完成"不代表真的完成了。每个工具动作必须有 evidence ref，任务结束必须通过 verification gate。
4.3.1 Evidence Ledger（JSONL append-only）
{"ts": "2026-05-22T10:30:01Z", "run_id": "r-001", "step": 3, "tool": "read", "args": {"path": "src/main.py"}, "result": {"lines": 120, "preview": "def main():..."}, "hash": "sha256:abc123"}
{"ts": "2026-05-22T10:30:05Z", "run_id": "r-001", "step": 4, "tool": "write", "args": {"path": "src/main.py"}, "result": {"wrote": 1250, "diff_hint": "added:3, removed:1"}, "hash": "sha256:def456"}
{"ts": "2026-05-22T10:30:10Z", "run_id": "r-001", "step": 5, "tool": "verify", "result": {"status": "blocked", "reason": "write to src/main.py: content hash mismatch"}}
**每条 evidence record 要求：**
`run_id` — 归属哪个 run
`step` — 递增步数
`tool` — 工具名
`args` — 输入参数（必脱敏）
`result` — 输出摘要
`hash` — 可验证的 content hash（文件写入时）
4.3.2 Verification Gate
class VerificationGate:
    """成功必须经过验证。验证失败不能标 success。"""

    def verify(self, outcome: StepOutcome) -> VerifyResult:
        """
        验证规则：
        1. write 操作：hash 目标文件，与 evidence 中的 hash 比对
        2. run 操作：exit_code == 0 且 output 非空（如有预期）
        3. 最终 done：所有 step 都 verified 或 blocked_reason 已记录
        4. 不能自验证：verification 本身不能由同一次 LLM 调用完成
        """
        return VerifyResult(
            status="verified" | "blocked" | "pending",
            reason=str,
            evidence_refs=list[str],
        )
**VerifyResult 三态：**
`verified` — 通过，可进入下一步
`blocked` — 失败，blocked_reason 写入 manifest
`pending` — 等待异步验证（如外部 API 回调）
4.3.3 Run Manifest（每次运行一个）

Run Manifest 记录**单次 Agent 运行**的完整轨迹——输入、步骤、验证结果、证据文件位置。
与 Evolution 层的 **Change Manifest** 不同：Run Manifest 是"这次做了什么"的操作记录，
Change Manifest（§4.7.2）是"我变了什么"的自省记录——记录技能结晶、记忆更新、
配置变更等系统自身的演化。

{
  "run_id": "r-20260522-001",
  "task": "修复 CI 配置中的 Python 版本错误",
  "started": "2026-05-22T10:30:00Z",
  "ended": "2026-05-22T10:32:15Z",
  "status": "success",
  "steps": 5,
  "tools_used": ["read", "write", "search"],
  "verification": {
    "verified_steps": 5,
    "blocked_steps": 0,
    "final_status": "verified"
  },
  "evidence_file": "runs/r-20260522-001/evidence.jsonl",
  "blocked_reason": null
}
4.3.4 Secret Redaction
SECRET_PATTERNS = [
    r'(?i)(api[_-]?key|token|secret|password|auth)\s*[:=]\s*[\'"][^\'"]+[\'"]',
    r'sk-[a-zA-Z0-9]{20,}',           # OpenAI/DeepSeek API key
    r'ghp_[a-zA-Z0-9]{36}',           # GitHub Personal Access Token (classic)
    r'github_pat_[a-zA-Z0-9_]{36,}',  # GitHub PAT (fine-grained)
    r'(?i)Bearer\s+[a-zA-Z0-9\-_\.]{20,}',  # Bearer token
    r'glpat-[a-zA-Z0-9\-_]{20,}',    # GitLab PAT
]

def redact_secrets(text: str) -> str:
    """在写入 manifest/log 前必须跑一遍。"""
    for pattern in SECRET_PATTERNS:
        text = re.sub(pattern, '[REDACTED]', text)
    return text
4.4 Memory Store

**5 层记忆体系（纯文件系统，零外部依赖）：**

```
L1: CORE     — 身份、配置、长期偏好（YINYO.md + SOUL.md，不可变自动注入）
L2: EPISODIC — 按 run_id 的事件记录（runs/<id>/evidence.jsonl + summary.md）
L3: SKILL    — 已结晶的可复用能力（skills/ 目录，版本化管理）
L4: CACHE    — 上下文缓存（Observation Masking 管理、LRU 淘汰）
L5: SHADOW   — 过期/待归档/推演中的记忆（agent 按需查阅）
```

**存储方式：纯文件系统（ByteRover Context Tree 风格）**

```python
# 不依赖外部包。所有记忆在项目目录下。
workspace/
├── YINYO.md           # L1: 核心记忆（自动注入 system prompt）
├── SOUL.md            # L1: 行为规则（自动注入 system prompt）
├── skills/            # L3: 已结晶技能
│   └── fix-python-version/
│       ├── SKILL.md
│       └── meta.json  # version, activation_count, last_used
├── runs/              # L2: 按 run 分目录
│   └── r-20260522-001/
│       ├── evidence.jsonl
│       ├── manifest.json
│       └── summary.md
└── cache/             # L4: Observation Masking 缓存
```

**为什么不做 agentmemory 集成：** v2.0 的 ADR-0005 声称集成 `agentmemory`，但 PyPI 上不存在此包（已查证）。48K+ stars 的数字来源无法重现。YINYO 改为纯文件系统自建存储——这是 `less is more` 的真实落地，也是修复全记录 §六·6.4 的教训：外部依赖可能不存在，文件系统永远可靠。

**SimpleMem 压缩（信息熵过滤，用于 L2 写入时）：**

注意与 Observation Masking 的分工：Masking 负责 L1 上下文窗口内的工具输出管理（运行时），
SimpleMem 负责 L2 写入时的语义压缩（持久化前）。两者不冲突——Masking 决策"当前保留什么"，
SimpleMem 决策"存什么到磁盘"。

```python
class SimpleMemCompressor:
    """保留高熵片段，丢弃低熵（问候语、确认词）。"""
    def compress(self, history: list, max_tokens: int) -> list:
        # 1. 计算每段信息熵
        # 2. 按熵排序，保留 top-K
        # 3. 低熵片段 → 一句话摘要
```

4.5 Model Gateway

**API 接入方式：** OpenAI 兼容 API（`POST /v1/chat/completions`，`https://api.deepseek.com`）。
与 fallback 的 OpenAI 兼容 API 统一路径，减少代码分支。不直接使用 DeepSeek SDK。

**分层模型策略：**
场景 | 模型 | Thinking | 说明
日常工具调用（80%） | V4-Flash | Non-think | 最快，$0.28/1M
任务分解/规划 | V4-Pro | Think High | 需正确决策
代码生成 | V4-Flash | Non-think | 够好
代码审查/分析 | V4-Pro | Think High | 深度分析有价值
连续 2 次失败 | V4-Pro | Think Max | 自动升级
记忆摘要 | V4-Flash | Non-think | 简单摘要
技能结晶 | V4-Pro | Think High | 跨 session 模式识别
**Thinking 模式分层：**
**编排层（~20% 调用）** → Think High
**执行层（~80% 调用）** → Non-think
**连续 2 次失败** → 自动升级到 Think Max
**用户可覆盖** → `agent = YinyoAgent(thinking_mode=ThinkingMode.STRATIFIED)`
**DeepSeek Context Caching：**
System prompt + 工具 schema 作为 cache 前缀
Cache hit 成本 ~1/280：
- Cache hit：$0.0028 / 1M tokens（系统 prompt + 工具 schema 命中缓存）
- Cache miss：$0.28 / 1M tokens（完整输入价格）
- 同一 session 内系统 prompt 和工具定义不变 → 极高命中率
同一 session 内极高命中率
**DeepSeek reasoning_content 回传规则（★ v2.1 补回，来自 v1 Spec）：**

DeepSeek V4 thinking 模式返回 `reasoning_content` 字段（模型内部推理链）。此字段**必须**在下轮请求中回传到 messages，否则 API 返回 HTTP 400。

```python
# 正确做法
if response.reasoning_content:
    messages.append({
        "role": "assistant",
        "content": response.content,
        "reasoning_content": response.reasoning_content  # ← 必须回传
    })

# 错误做法（会 HTTP 400）
messages.append({"role": "assistant", "content": response.content})
# reasoning_content 丢了 → 下一轮 thinking 模式请求会报错
```

**关键特性：** `reasoning_content` 不占 context window——DeepSeek 在下一轮请求中自动剥离推理 token，只保留 `content` 进入上下文。这意味着模型"想了但不占座"，对 Agent 架构非常友好。

**Thinking 模式参数约束（★ v2.1 补回）：**

thinking 模式下，temperature、top_p 等采样参数被 API **静默忽略**。代码中不应传递这些参数（传了无效还会造成困惑）。

```python
if thinking_mode != "non-think":
    # 不传 temperature/top_p——会被 API 忽略
    params = {"model": model, "messages": messages}
else:
    params = {"model": model, "messages": messages, "temperature": 0.0}
```

**Fallback：**
V4-Flash 失败 → V4-Pro（不静默，记录到 manifest）
DeepSeek 不可用 → OpenAI 兼容 API（需显式配置）
不允许静默 fallback
4.6 Governance & Safety ★ 新增

4.7 Evolution — 技能结晶与自演化

**设计动机：** YINYO 不预设技能，能力通过工具 + 记忆 → 技能结晶获得。这是 YINYO 相比
GenericAgent 的关键差异化——GA 的自结晶基于工具序列固化，YINYO 在此基础上加入 Change Manifest 自省。

4.7.1 技能结晶状态机

```
触发条件：同一工具序列（3+ tool calls）出现 3 次
    │
    ▼
┌─────────┐
│  DRAFT   │  自动创建 skills/<hash>/SKILL.md
└────┬────┘  技能标注为 draft，不会被自动激活
     │
     │ 5 次无 blocked 执行
     ▼
┌─────────┐
│  PROVEN  │  通过验证，可被 Agent 自主调用
└────┬────┘
     │
     │ 10 次成功 + 人类 review（可选）
     ▼
┌─────────┐
│  STABLE  │  固化技能，版本化（v1.0.0）
└─────────┘
```

```python
from dataclasses import dataclass, field
from enum import Enum

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
        self.patterns: dict[str, int] = {}  # hash(tool_sequence) → count

    def observe(self, tool_sequence: list[str]) -> Skill | None:
        """每次任务结束后调用，检测是否有可结晶的序列。

        Returns:
            Skill 对象（如果触发结晶）或 None
        """
        if len(tool_sequence) < 3:
            return None

        seq_hash = hashlib.sha256("→".join(tool_sequence).encode()).hexdigest()[:8]
        self.patterns[seq_hash] = self.patterns.get(seq_hash, 0) + 1

        if self.patterns[seq_hash] >= 3:
            skill = self._crystallize(seq_hash, tool_sequence)
            self._write_change_manifest(skill, tool_sequence)
            return skill
        return None

    def _crystallize(self, seq_hash: str, sequence: list[str]) -> Skill:
        """将工具序列写入 SKILL.md 文件。"""
        skill_dir = f"{self.workspace}/skills/{seq_hash}"
        os.makedirs(skill_dir, exist_ok=True)

        skill_md = f"""# Skill: {seq_hash}
status: draft
activation_count: 3
tools: {sequence}

## 工具序列
{"".join(f"{i+1}. {t}\n" for i, t in enumerate(sequence))}
## 触发条件
同一工具序列出现 3 次后自动结晶。
## 验证状态
draft — 未经验证，不会自动激活。
"""
        with open(f"{skill_dir}/SKILL.md", "w") as f:
            f.write(skill_md)

        meta = {"name": seq_hash, "status": "draft", "tools": sequence,
                "activation_count": 3, "created_at": datetime.now().isoformat()}
        with open(f"{skill_dir}/meta.json", "w") as f:
            json.dump(meta, f, indent=2)

        return Skill(name=seq_hash, status=SkillStatus.DRAFT, activation_count=3)

    def promote(self, skill: Skill) -> Skill:
        """升级技能：draft → proven → stable。"""
        if skill.status == SkillStatus.DRAFT and skill.activation_count >= 5:
            skill.status = SkillStatus.PROVEN
            skill.version = "0.5.0"
        elif skill.status == SkillStatus.PROVEN and skill.activation_count >= 10:
            skill.status = SkillStatus.STABLE
            skill.version = "1.0.0"
        self._update_meta(skill)
        return skill
```

4.7.2 Change Manifest — Agent 自省基础

**与 Run Manifest 的关系：**
- **Run Manifest** (§4.3.3)：记录"这次任务做了什么"——每次运行一个，存 `runs/<run_id>/manifest.json`
- **Change Manifest**：记录"我（Agent 自身）变了什么"——技能结晶、记忆更新、配置变更。追加式写入 `changes.jsonl`

```json
{"ts": "2026-05-22T10:32:20Z", "type": "skill_crystallized", "detail": {"skill": "a3f2c1d8", "tools": ["read", "search", "write"], "status": "draft"}}
{"ts": "2026-05-22T14:15:00Z", "type": "skill_promoted", "detail": {"skill": "a3f2c1d8", "from": "draft", "to": "proven"}}
{"ts": "2026-05-22T14:20:00Z", "type": "memory_updated", "detail": {"layer": "L2", "run_id": "r-20260522-005", "summary": "修复 Docker 构建缓存的 3 种策略"}}
{"ts": "2026-05-22T14:25:00Z", "type": "config_changed", "detail": {"key": "max_steps", "from": 30, "to": 50}}
```

**记录的事件类型：**
| 类型 | 触发条件 |
|------|---------|
| `skill_crystallized` | 工具序列 3 次 → Draft |
| `skill_promoted` | Draft → Proven / Proven → Stable |
| `memory_updated` | L2 episodic 写入新摘要 |
| `config_changed` | 任何配置项被 Agent 或用户修改 |
| `self_check_passed` / `self_check_failed` | 启动自检结果 |

4.7.3 Self-Check — 启动时自检 + 按需诊断

```python
class SelfCheck:
    """启动时自检 Agent 状态，返回诊断报告。"""

    def run(self, workspace: str) -> SelfCheckReport:
        checks = []

        # 1. 目录完整性
        for d in ["skills", "runs", "cache"]:
            if not os.path.isdir(f"{workspace}/{d}"):
                checks.append(CheckItem(f"missing_dir:{d}", "FAIL",
                                        f"Directory {d} not found"))

        # 2. 记忆层完整
        for f in ["YINYO.md", "SOUL.md"]:
            if not os.path.isfile(f"{workspace}/{f}"):
                checks.append(CheckItem(f"missing_memory:{f}", "WARN",
                                        f"Memory file {f} not found"))

        # 3. 技能版本一致性
        for skill_dir in glob(f"{workspace}/skills/*/meta.json"):
            meta = json.load(open(skill_dir))
            if meta.get("status") == "draft" and meta.get("activation_count", 0) > 5:
                checks.append(CheckItem(f"stale_skill:{meta['name']}", "WARN",
                                        "Skill stuck in draft despite 5+ activations"))

        # 4. Evidence 完整性
        evidence_files = glob(f"{workspace}/runs/*/evidence.jsonl")
        for ef in evidence_files:
            if os.path.getsize(ef) == 0:
                checks.append(CheckItem(f"empty_evidence:{ef}", "WARN",
                                        "Evidence file is empty"))

        return SelfCheckReport(
            passed=all(c.level != "FAIL" for c in checks),
            checks=checks,
            summary=f"{sum(1 for c in checks if c.level == 'FAIL')} FAIL, " + 
                    f"{sum(1 for c in checks if c.level == 'WARN')} WARN, " +
                    f"{sum(1 for c in checks if c.level == 'PASS')} PASS",
        )
```

**自动触发规则（5 条）：**
| # | 条件 | 动作 |
|---|------|------|
| 1 | Agent 启动 | 自动跑 SelfCheck，结果写入 Change Manifest |
| 2 | 技能 status=draft 但 activation_count > 5 | 自动 promote 到 proven |
| 3 | 发现新的工具序列模式 | 触发 SkillCrystallizer.observe() |
| 4 | 连续 3 次 verification blocked | 记录到 Change Manifest，标记为 anomaly |
| 5 | 检测到 YINYO.md / SOUL.md 被外部修改 | WARN，不自动覆盖 |


class RiskPolicy:
    """高风险动作必须拦截。"""

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

    def gate(self, action: Action) -> GateResult:
        if action.type in self.BLOCK_ALWAYS:
            return GateResult("blocked", reason=f"{action.type} is blocked by risk policy")
        if action.type in self.CONFIRM_REQUIRED:
            return GateResult("confirm", prompt=f"Confirm {action.type}?")
        return GateResult("allow")
**Secret Scanner：**
每次写入 manifest/log 前自动扫描
匹配 API key / token / password / Bearer 等模式
命中的替换为 `[REDACTED]`
记录 redaction 事件到 evidence
5. 架构决策记录 (ADR)
ADR-0001：定位 — compact DeepSeek-first Harness Engineer
**背景：** 有 Hermes（50K+ 行通用 Agent 平台）和 OpenClaw（成熟生态），YINYO 做什么？
**决策：** YINYO 不做通用平台。定位为 compact DeepSeek-first Harness Engineer Agent。核心 < 800 行。
**理由：**
Hermes/OpenClaw 已解决"大而全"的问题
YINYO 的价值在"小而精"：极简 Agent Loop + 证据链 + 自演化
DeepSeek V4 有独特优势（1M context、Context Caching、分层 Thinking），值得原生优化
ADR-0002：证据链优先于功能堆叠
**背景：** v1 Spec 缺少验证机制。Agent 自报"完成"不可信。
**决策：** Evidence Ledger + Verification Gate 是核心功能，不是附加功能。没有验证的任务不能标 success。
**理由：**
模型幻觉是现实问题，不能假设 Agent 的自我报告可靠
JSONL append-only 提供不可篡改的审计轨迹
这是 YINYO 相比 smolagents/OpenHarness 的核心差异化
ADR-0003：Observation Masking > LLM Summarization
**背景：** JetBrains 2025 实验证明 Masking 比 Summary 好 2.6%、便宜 52%。
**决策：** Context Manager 第一层用 Observation Masking（保留最近 N 个工具输出），只在 token 超过阈值时才升级到 LLM 压缩。
**理由：**
零推理成本，不增加延迟
有实验数据支撑，不是直觉
DeepSeek 1M context 让 Masking 更可行（阈值更高）
ADR-0004：Code Agent 是默认模式
**背景：** Smolagents 实验证明 Code Agent 比 JSON tool-calling 步骤少 30%、出错率低。
**决策：** YINYO 默认使用 Code Agent 模式，JSON tool-calling 作为 fallback。
**理由：**
- Smolagents 实验证明 Code Agent 比 JSON tool-calling 步骤少 30%、出错率更低（huggingface/smolagents, 2025）
- 模型写代码比手写 JSON tool-calling 更自然——代码可以包含条件逻辑和循环，减少往返次数
- SimpleExec 提供语法级沙箱保护
- DeepSeek V4 代码生成能力已验证
ADR-0005：纯文件系统存储，零外部记忆依赖
**背景：** v2.0 曾计划集成 `agentmemory`，但 PyPI 上不存在此包（已查证）。48K+ stars 的数字无法重现。
**决策：** L1-L5 全部用纯文件系统（ByteRover Context Tree 风格）。不上向量库、不上图库、不上外部记忆服务。
**理由：**
文件系统永远可用，无版本兼容问题
`less is more` 的真实落地：不引入不存在的依赖
修复全记录 §六·6.4 的教训：外部依赖消失 → 系统崩溃。文件系统不会消失
SimpleMem 的信息熵过滤 + Observation Masking 已经足够覆盖 YINYO 的记忆需求
ByteRover 论文验证了纯文件系统做 Agent 记忆的可行性（Context Tree + AKL 生命周期）
6. Phase Plan
Phase 1 — Skeleton（无模型调用）
**目标：** 先跑通结构，验证 schema 和 evidence 系统。
yinyo run examples/minimal-task.yaml
**Must pass:**
[ ] 生成 `runs/<run_id>/manifest.json`（schema-valid）
[ ] 生成 `runs/<run_id>/evidence.jsonl`
[ ] `yinyo inspect <run_id>` 可读
[ ] `yinyo verify <run_id>` 可返回 verified/blocked/failed
[ ] Risk policy gate 生效（高风险动作被拦截）
[ ] Secret redaction 结构就位（扫描逻辑可用，Phase 3 接入真实工具输出后验收功能正确性）
Phase 2 — DeepSeek Adapter
**目标：** 先 mock，再真 API。
**Must pass:**
[ ] Mock mode：fake response → 正确解析
[ ] Real mode：V4-Flash 调用成功
[ ] Thinking 分层：Non-think / Think High / Think Max 切换正确
[ ] Context Caching：cache hit 识别
[ ] Bounded retry（最多 2 次，指数退避）
[ ] No silent fallback（切换模型时记录到 manifest）
[ ] Timeout works
[ ] Redacted request/response logging
Phase 3 — Tool Adapters
**目标：** 5 个原子工具全部走 evidence ledger。
**Must pass:**
[ ] 每个工具动作都有 evidence ref
[ ] `do_run` 支持 timeout
[ ] `do_write` 记录 path + diff hint + content hash
[ ] `do_read` 拦截敏感文件（.env, .key, .token, *.pem）
[ ] 权限三态（ALLOW/CONFIRM/BLOCK）生效
[ ] User-defined YAML tools 可加载
Phase 4 — Loop Integration
**目标：** 闭环 plan → act → observe → verify → persist。
**Must pass:**
[ ] Code Agent 模式跑通完整任务
[ ] JSON Tool-Calling fallback 跑通
[ ] Success 必须经过 verification gate
[ ] Verification 失败时 blocked_reason 写入 manifest
[ ] Context Manager 三层自动升降生效
[ ] SimpleExec sandbox 拦截危险 import/call
Phase 5 — Governance & Evolution Hardening
**目标：** 把风险边界和自演化固化进 runtime。
**Must pass:**
[ ] Secret scan for logs/manifests（每次写入前）
[ ] High-risk action gate（block by default 的列表生效）
[ ] Provider/config mutation blocked by default
[ ] Failure mode tests（网络断开、API 限流、非法输入）
[ ] 技能结晶触发准确（3 次 → draft）
[ ] Change Manifest 正确记录所有变更
[ ] Self-check 报告准确
7. 验收标准
**YINYO MVP 可进入下一阶段的条件：**
所有 schema 可被 JSON Schema validator 解析
Example task 能跑通（Phase 1 mock）
Manifest 符合 schema
Evidence ledger 不含 secret
DeepSeek adapter mock/real 模式边界清楚
Verification 失败时不会返回 success
Risk policy 拦截清单内的所有高风险动作
README/docs 能解释边界和架构
Codex handoff 能直接开工（`handoff/YINYO-CODEX-HANDOFF.md`）
8. 附录
8.1 调研基础
本 Spec 整合了三方输入：
**隐曜 v1 Spec：**
GenericAgent (arXiv 2604.17091)、Smolagents、ByteRover、SimpleMem、Mem0
Anthropic Context Engineering、DeepSeek V4 文档
**大管家 Spec：**
Agent Harness Survey (Meng 2026)、AHE (复旦+北大)、NLAH (清华)
Externalization Survey (2026)、AutoHarness (Cornell)、Trace2Skill (2026)
JetBrains Context (2025)：Observation Masking > LLM Summarization
smolagents、OpenHarness、agentmemory 源码
**OpenClaw Spec：**
Evidence Ledger + Verification Gate 设计
ADR 模板、Run Manifest schema
Phase plan 验收标准
8.2 竞品对照表
维度 | smolagents | OpenHarness | Hermes | **GenericAgent** | **YINYO v2.1**
核心代码 | ~1200 | >5000 | ~8000 | ~600 | **~700 + 400**
Agent Loop | ~40 生成器 | 事件驱动 | 事件驱动 | ~50 行 StepOutcome | **plan→act→observe→verify→persist**
记忆 | AgentMemory | auto-compact | File+SQLite | 5层文件系统 | **5层 + Observation Masking**
证据链 | ❌ | ❌ | ❌ | ❌ | **✅ Evidence Ledger**
验证门 | ❌ | ❌ | ❌ | ❌ | **✅ Verification Gate**
技能演化 | ❌ | ❌ | ❌ | ✅ 自结晶 | **✅ 自结晶 + Change Manifest**
DeepSeek 优化 | 通用 | 通用 | 适配 | 通用 | **✅ Context Caching + 分层 Thinking**
安全 | 基础 | 基础 | 完善 | 基础 | **✅ Risk Policy + Secret Scan**
8.3 v1 → v2 变更清单
变更 | 来源 | 说明
★ 新增 Evidence Engine | OpenClaw | Evidence Ledger + Verification Gate + Run Manifest
★ 新增 Governance | OpenClaw | Risk Policy + Secret Scan + Permission 三态
★ 新增 ADR | OpenClaw | 5 个架构决策记录
★ 吸收 Observation Masking | 大管家 | 替换纯 LLM 压缩，成本 -52%、效果 +2.6%
★ 吸收 agentmemory 集成 | 大管家 | ⚠️ v2.1 已撤回：PyPI 无此包，改纯文件系统
★ 吸收 YINYO 不做的事 | 大管家 | 8 条明确边界
★ 新增 Phase Plan + 验收标准 | OpenClaw | 6 阶段 + 9 条验收
保留 Code Agent 默认 | 隐曜 v1 | Smolagents 实验支撑
保留分层 Thinking | 隐曜 v1 | DeepSeek V4 原生特性
保留 5 层记忆 | 隐曜 v1 | 简化 + agentmemory 集成
保留技能结晶 | 隐曜 v1 | 自演化核心
保留 Change Manifest | 隐曜 v1 | agent 自省基础
**本 Spec 版本：** v2.0 | **最后更新：** 2026-05-22
**融合来源：** 隐曜 v1 + 大管家 + OpenClaw 三方 Spec 深度比对后重新整合
**下一步：** 正元审阅 → 确认 v2 Spec → 进入 Phase 1 Skeleton Implementation


8.4 v2.0 → v2.1 变更清单

| 变更 | 来源 | 说明 |
|------|------|------|
| ★ 新增 Context Management 核心原则 | Hermes 修复全记录 | §2.0：三条铁律（压缩失败不丢消息、不自发跨 session 检索、provider 写死） |
| ★ 重写 Context Manager | Hermes 修复全记录 + LCM | §4.2：DAG 无损归档 + 安全降级规则 + 跨 session 检索约束 + Context Budget Allocator |
| ★ 撤回 agentmemory 集成 | PyPI 查证 | ADR-0005 重写：纯文件系统。`from agentmemory import MemoryStore` 已删除 |
| ★ 修正 Memory Store | ByteRover | §4.4：5 层纯文件系统 + 目录结构示例 |
| △ 更新不做的事清单 | Hermes 修复全记录 | §2.3：新增"不自发跨 session 检索"、"provider 不用 auto" |
| △ 新增第 6 条核心原则 | Hermes 修复全记录 | §2.1：三层记忆隔离 |
| △ Context Manager 行数调整 | 实际设计复杂度 | 150→200 行（新增 DAG + 安全降级逻辑） |
