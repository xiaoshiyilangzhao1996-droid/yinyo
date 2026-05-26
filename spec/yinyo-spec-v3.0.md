YINYO Harness Agent — 架构完整 Spec v3.0
**纲领：** Less is more。纯 ReAct，不用 Code Agent。DeepSeek 高适配。
**定位：** 一个 compact DeepSeek-first Harness Agent runtime。
**范围：** 核心运行时 ~400 行 Python。7 个原子工具。
**版本：** v3.0 | **日期：** 2026-05-24
**核心变更：** Code Agent → 纯 ReAct 模式。工具 schema 注入 system prompt。7 个工具包含 do_read / do_write / do_search / do_run / do_ask / do_edit / do_patch。通过率从 48.9% 跃升至 97.8%。

目录
[终局判词](#1-终局判词)
[设计原则与边界](#2-设计原则与边界)
[架构总览](#3-架构总览)
[组件规范](#4-组件规范)
[架构决策记录 ADR](#5-架构决策记录-adr)
[Phase Plan](#6-phase-plan)
[验收标准](#7-验收标准)
[审计修复清单](#8-审计修复清单)

---

## 1. 终局判词

YINYO v3.0 是一套紧凑的 ReAct Agent 运行时，以 DeepSeek 为核心推理引擎，
通过工具调用接口与环境交互。

终极判词：
**"Less is more。回归原点：Think → Act → Observe → Repeat。代码即证据。"**

## 2. 设计原则与边界

### 2.1 三原则

1. **Less is more** — 代码精简，攻击表面最小化。不必要的抽象 = 额外的事故入口。
2. **DeepSeek 高适配** — 工具 schema 以 OpenAI tool-calling 格式发送。
   利用 DeepSeek 的并行工具调用特性（未来版本）。
3. **纯 ReAct 循环** — Think → Act → Observe → Repeat。
   不做 Code Agent 模式（不强求 LLM 输出完整 Python 代码）。

### 2.2 边界

**包含：**
- ReAct 循环（灵感来自 ReAct Prompting, Yao et al. 2022）
- 7 个原子工具（文件读写、搜索、执行、提问、编辑、补丁）
- DeepSeek API 网关 + 3 种 thinking 模式
- 嵌入式 Evidence Ledger（证据可审计）
- 基础 Governance（风险策略 + 密钥扫描）

**明确不包含（留给未来版本）：**
- Plan 阶段（v4.0）
- VectorCache 语义检索（v4.0）
- 并行工具调用（v4.0）
- 记忆体系（v6.0）
- 飞书适配（v5.0）
- 技能自进化（v8.0）

## 3. 架构总览

```
User Input
    │
    ▼
┌─────────────────────────────┐
│  System Prompt              │
│  (AGENTS.md + Tool Schemas) │
└──────────┬──────────────────┘
           │
           ▼
    ╔══════════════╗
    ║  ReAct Loop   ║──────────────────────────────┐
    ║               ║                              │
    ║  Think ──► Act ──► Observe ──► Repeat       │
    ╚══════╤════════╝                              │
           │                                       │
    ┌──────▼──────┐    ┌──────────────┐    ┌──────▼──────┐
    │  Model       │    │  Tool        │    │  Evidence   │
    │  Gateway     │───►│  Registry    │───►│  Ledger     │
    └─────────────┘    │  (7 tools)   │    └─────────────┘
                       └──────┬───────┘
                              │
                       ┌──────▼───────┐
                       │  Governance  │
                       │  Gate        │
                       └──────────────┘
```

### 3.1 文件结构

```
yinyo/
├── agent.py       ~300行  主 Agent ReAct 循环
├── tools.py       ~400行  7 个原子工具 + 注册
├── evidence.py    ~100行  Evidence Ledger（JSONL 存证）
├── governance.py  ~80行   风险策略 + 密钥扫描
├── model.py       ~150行  模型网关（3 种 thinking 模式）
└── __init__.py    20行   包导出
```

## 4. 组件规范

### 4.1 agent.py — 主循环

```
class AgentSession:
    - workspace: 工作目录
    - model: ModelGateway 实例
    - governance: RiskPolicy 实例
    - max_steps: 最大 ReAct 步数（默认 50）

    run(task) → dict:
        1. 构建系统提示（AGENTS.md + 工具 schema）
        2. 启动 ReAct 循环
        3. 每步：LLM 推理 → 工具调用 → 证据记录 → 观察 → 下一步
        4. 返回 {status, summary, steps, tool_sequence}

_v1_react():
    Think → Act → Observe → Repeat
    纯文本推理（thinking），工具调用，观察结果。
    不做 Plan，不做 Reflect。
```

### 4.2 tools.py — 工具系统

7 个原子工具：

| 工具 | 权限 | 功能 |
|:--|:--|:--|
| do_read | ALLOW | 读取文件，返回行号内容 |
| do_write | CONFIRM | 写入文件，返回 SHA256 hash |
| do_search | ALLOW | 搜索文件内容或文件名 |
| do_run | CONFIRM | 执行 shell 命令 |
| do_ask | ALLOW | 向模型提问（子查询） |
| do_edit | CONFIRM | 定向文本替换 |
| do_patch | CONFIRM | V4A 格式补丁应用 |

ToolRegistry 负责注册和分发。execute_tool_with_evidence 负责 Governance Gate → 执行 → Secret Scan → Evidence Record 完整管线。

### 4.3 model.py — 模型网关

- 3 种 thinking 模式：THINK_OFF / THINK_HIGH / THINK_MAX
- 自动 retry（最多 3 次）
- Mock 模式支持（无需 API key）
- Chat Completion API 封装

### 4.4 governance.py — 治理层

- RiskPolicy：BLOCK_ALWAYS / CONFIRM_REQUIRED 策略
- gate_for_tool：按工具名和参数判断风险
- SECRET_PATTERNS：密钥正则扫描
- scan_secrets / redact_secrets

### 4.5 evidence.py — 证据引擎

- EvidenceLedger：JSONL append-only 记录
- _redact_args：写入前自动脱敏
- 每次工具调用生成 hash ref

## 5. 架构决策记录 ADR

| # | 决策 | 原因 |
|:--|:--|:--|
| ADR-01 | 选择 ReAct 而非 Code Agent 模式 | v2.1 的 Code Agent 模式通过率仅 48.9%；工具 schema 注入 system prompt 后 LLM 正确调用率 97.8% |
| ADR-02 | 工具 schema 注入 system prompt | DeepSeek 需要显式看到工具定义才能正确调用 |
| ADR-03 | 不做 parallel tool calls | 留到 v4.0，先验证单工具调用稳定性 |
| ADR-04 | 不做 Plan 阶段 | ReAct = Think → Act，Think 本身就是轻量 Plan |

## 6. Phase Plan

| Phase | 内容 | 状态 |
|:--|:--|:--|
| Phase 1 | ReAct 循环 + 7 工具 + Governance | ✅ v3.0 |
| Phase 2 | Evidence Ledger + 密钥扫描 | ✅ v3.0 |
| Phase 3 | 并行工具调用 + Plan 阶段 | 🔜 v4.0 |
| Phase 4 | VectorCache 语义检索 | 🔜 v4.0 |

## 7. 验收标准

- [x] ReAct 循环正常运行（7 工具 dispatch 正确）
- [x] 盲测通过率 ≥ 97%
- [x] evidence.jsonl 记录完整
- [x] 密钥扫描拦截敏感输出
- [x] pytest 57/57 通过

## 8. 审计修复清单

| # | 问题 | 严重度 | 修复 |
|:--|:--|:--|:--|
| 1 | Code Agent 模式通过率仅 48.9% | 高危 | 改为 ReAct |
| 2 | 工具 schema 不完整 | 中危 | 注入 system prompt |
| 3 | 缺少 evidence 记录 | 中危 | EvidenceLedger |
| 4 | 密钥可能泄露 | 高危 | SECRET_PATTERNS |

---

*Spec v3.0 生成于 2026-05-24。本文件覆盖了被 v4.0 误覆盖的原 v3.0 内容。*
*恢复日期：2026-05-26*
