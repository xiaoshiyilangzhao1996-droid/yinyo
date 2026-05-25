# YINYO（隐曜）—— 会自主进化的飞书 AI Agent

**YINYO** 是一个为**飞书（Lark）**设计的自进化 AI Agent。它不是 CLI 框架，也不是 chatbot 套壳——它是一个拥有完整认知层（SOUL、AGENTS、USER、MEMORY）、持久记忆自动反思、DeepSeek 深度适配的独立 Agent 产品。

> "说飞书的语言，用 DeepSeek 思考，在每一次对话中进化。"

---

## 核心特性

| 特性 | 说明 |
|------|------|
| **飞书原生** | Card 2.0 消息、长文本分段、标题降级、防截断。飞书 12 项体验全部绿灯。 |
| **ReAct + Plan 循环** | 纯 ReAct 循环 + 轻量 Plan 阶段。并行工具调用。最多 50 步。 |
| **LLM 驱动记忆** | USER.md + MEMORY.md（注入式）、VectorCache（TF-IDF 语义检索）、每次 run 后自动反思、每 10 次 run 深度反思。 |
| **自我进化** | 从重复工具模式中结晶技能。变更清单。初始化自检。 |
| **证据锚定** | 每次工具调用哈希存证。验证关。运行清单。 |
| **DeepSeek 优化** | 128K 上下文窗口充分利用。LLM 压缩取代规则。兼容 Context Caching。 |
| **8 个原子工具** | read、write、patch、search、execute、web、web_think、do_memory——最小接口面，最大能力。 |
| **风险治理** | 风险策略引擎。拦截步骤追踪。连续失败时自动升级思考深度。 |

---

## 快速开始

### 安装

```bash
pip install yinyo-agent
```

### 使用

```python
from yinyo import YinyoAgent

agent = YinyoAgent(workspace="./my_workspace")

# 处理飞书消息
response = agent.handle_message(
    user_id="ou_xxx",
    chat_id="oc_xxx",
    text="帮我查一下最近 3 天的天气"
)

# 或直接运行任务
result = agent.run("分析这份数据并生成报告")
```

### 环境配置

```bash
export DEEPSEEK_API_KEY="sk-..."
```

---

## 架构

```
用户消息（飞书）
        │
        ▼
┌───────────────────┐
│  Session Manager  │  去重、命令路由、对话历史
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│   YinyoAgent.run  │  核心循环入口
└────────┬──────────┘
         │
    ┌────▼────┐
    │  Plan   │  轻量步骤规划（可选）
    └────┬────┘
         │
    ┌────▼────────────────────────────────┐
    │           ReAct 循环                │
    │  ┌──────────┐    ┌──────────────┐   │
    │  │  Model   │───▶│  工具调用    │   │
    │  │ Gateway  │◀───│  (并行)      │   │
    │  └──────────┘    └──────┬───────┘   │
    │                         │           │
    │  ┌──────────────────────▼────────┐  │
    │  │  证据链 + 验证                │  │
    │  └───────────────────────────────┘  │
    └─────────────────────────────────────┘
         │
    ┌────▼────────────────────┐
    │  自动反思 + 记忆更新    │
    │  深度反思（每 10 次）   │
    └─────────────────────────┘
```

## 核心组件

| 组件 | 文件 | 行数 | 职责 |
|------|------|------|------|
| Agent 循环 | `agent.py` | 303 | ReAct + Plan + Reflect |
| 上下文管理 | `context.py` | 192 | LLM 压缩、掩码、检索 |
| 记忆存储 | `memory.py` | ~200 | 情景记忆 + 向量缓存 |
| 记忆工具 | `memory_tool.py` | ~170 | USER.md/MEMORY.md 增删改 |
| 模型网关 | `model.py` | ~150 | DeepSeek API + 思考模式 |
| 工具注册表 | `tools.py` | ~200 | 8 个工具 + YAML 加载 |
| 飞书适配 | `feishu_adapter.py` | 372 | 消息解析、会话路由 |
| 飞书卡片 | `feishu_card.py` | 77 | Card 2.0 构建器 |
| 飞书格式化 | `feishu_format.py` | 201 | Markdown → 飞书格式 |
| 会话管理 | `session.py` | 156 | 按用户/群的会话状态 |
| 风险治理 | `governance.py` | ~50 | 风险策略 |
| 证据链 | `evidence.py` | ~150 | 哈希存证工具调用 |
| 进化引擎 | `evolution.py` | ~100 | 技能结晶、自检 |

**总计：约 2,700 行纯 Agent 逻辑。**

---

## 版本历史

| 版本 | 日期 | 关键变更 | 通过率 |
|------|------|----------|--------|
| v8.1 | 2026-05-25 | AHE 工程层、57 项测试套件、可编程 mock | 100% |
| v8.0 | 2026-05-25 | Dual-Process 记忆、Vision、子Agent、Provider Chain、Trace2Skill | 100% |
| v7.0 | 2026-05-25 | LLM 压缩、自动/深度反思、AGENTS.md | 100% |
| v6.0 | 2026-05-24 | USER.md、MEMORY.md、do_memory 工具 | 100% |
| v5.0 | 2026-05-23 | 独立飞书产品、飞书 12 项适配 | 100% |
| v4.0 | 2026-05-22 | 并行工具调用、Plan 阶段、VectorCache | 100% |
| v3.0 | 2026-05-21 | Code Agent → 纯 ReAct | 97.8% |
| v2.1 | 2026-05-20 | 初始架构 | 48.9% |

详见 [CHANGELOG.md](CHANGELOG.md)。

---

## 文档

| 文档 | 内容 |
|------|------|
| [AGENTS.md](AGENTS.md) | 开发宪章——铁律、血泪教训、质量标准 |
| [SOUL.md](yinyo/SOUL.md) | Agent 身份与人格 |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 贡献指南 |
| [SECURITY.md](SECURITY.md) | 安全策略与信任模型 |
| [spec/](spec/) | 版本变更规格说明 |

---

## 设计原则

1. **Less is more** — 毙掉 10+ 非核心功能。每个功能必须有存在价值。
2. **集百家之长** — 每个设计背后都有论文（ACON、Plan-and-Solve、CASS、Mem0）或一线 Agent 实践支撑。
3. **DeepSeek 深度适配** — 充分利用 128K 上下文、并行 tool calls、极低成本。能用 LLM 的不用规则。

---

## 许可证

MIT © 2026 王正元 (Yinyo Contributors)
