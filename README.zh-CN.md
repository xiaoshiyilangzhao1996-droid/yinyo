<p align="center">
  <pre>
  ██╗   ██╗██╗███╗   ██╗██╗   ██╗ ██████╗ 
  ╚██╗ ██╔╝██║████╗  ██║╚██╗ ██╔╝██╔═══██╗
   ╚████╔╝ ██║██╔██╗ ██║ ╚████╔╝ ██║   ██║
    ╚██╔╝  ██║██║╚██╗██║  ╚██╔╝  ██║   ██║
     ██║   ██║██║ ╚████║   ██║   ╚██████╔╝
     ╚═╝   ╚═╝╚═╝  ╚═══╝   ╚═╝    ╚═════╝ 
  </pre>
</p>

# YINYO（隐曜）☤

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/xiaoshiyilangzhao1996-droid/yinyo"><img src="https://img.shields.io/badge/Built%20by-Yinyo%20Contributors-blueviolet?style=for-the-badge" alt="Built by Yinyo Contributors"></a>
  <a href="README.md"><img src="https://img.shields.io/badge/Lang-English-lightgrey?style=for-the-badge" alt="English"></a>
</p>

**为飞书（Lark）设计的自进化 AI Agent。** 它不是一个 CLI 框架，也不是 chatbot 套壳——它是一个拥有完整认知层（SOUL、AGENTS、USER、MEMORY）、基于论文前沿的 Dual-Process + TemporalTree 记忆架构、用 LLM 驱动的自进化引擎的独立 Agent 产品。

深度绑定 DeepSeek（128K → 1M 上下文，token 便宜到可以不计成本地保留对话全貌），只适配飞书一个平台——因为做好一件事，比什么都做但什么都做不好更有价值。

<table>
<tr><td width="180"><b>飞书原生，不做加法</b></td><td>Card 2.0 消息、长文本分段、标题降级、防截断。12 项飞书体验全部绿灯。消息发送、图片解析、会话路由——开箱即用，不是"支持飞书"，是"为飞书而生"。</td></tr>
<tr><td><b>论文前沿的记忆架构</b></td><td>Dual-Process（情景保留 + 语义提取）+ TemporalTree（时间层级树，事实可以<strong>演进取代</strong>而非只追加）+ 多范围检索。基于三篇 2026 年论文（Mem0 ECAI 2025, Dual-Process arXiv:2605.17625, TiMem arXiv:2601.02845），不是拍脑袋的设计。</td></tr>
<tr><td><b>会反思，会进化</b></td><td>每次对话结束自动反思，每 10 次深度反思。从重复失败中自动提取技能（Trace2Skill）。AHE 工程层：每次变更自动生成 Change Manifest，盲测通过自动标记 verified，失败自动回滚。</td></tr>
<tr><td><b>自建子 Agent，不让主 Agent 膨胀</b></td><td>监督者-工人模式，子 Agent 共享完整上下文（遵循 Cognition.ai 两原则）。盲测审计完全由子 Agent 执行，开发和测试严格分离——v2.1 自审 48.9%，独立盲审后连续 6 个版本 100%。</td></tr>
<tr><td><b>能看图</b></td><td>收到飞书截图自动识别内容，做分析或转述。外部视觉模型做 adapter，随时可替换。</td></tr>
<tr><td><b>Provider 挂了自动降级</b></td><td>同 provider 内 DeepSeek Flash → Pro 自动降级。跨 provider DeepSeek → z.ai/GLM 保底。不挂。</td></tr>
<tr><td><b>证据锚定，落盘才闭环</b></td><td>每次工具调用哈希存证。验证关。运行清单。不编造"用户已确认"。文件能 <code>stat</code>、URL 能 <code>curl</code>、测试能过，才算做完。</td></tr>
</table>

---

## 快速安装

```bash
pip install yinyo-agent
```

### 环境变量

```bash
export DEEPSEEK_API_KEY="sk-..."    # 必需
export VISION_API_KEY="sk-..."      # Vision 功能必需（可选）
export GLM_API_KEY="..."            # 跨 provider 降级用（可选）
```

---

## 快速开始

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

### CLI 参考

| 操作 | 命令 |
|------|------|
| 处理飞书消息 | `agent.handle_message(user_id, chat_id, text)` |
| 运行任务 | `agent.run("任务描述")` |
| 查看记忆 | `agent.memory.get_memory_summary()` |
| 运行测试 | `pytest tests/ -v` |
| 查看版本 | `python -c "from yinyo import __version__; print(__version__)"` |

---

## 和 Hermes / OpenClaw 的定位差异

YINYO **不和 Hermes 抢通用 Agent 市场**。Hermes 是一个 167K star 的航母级通用 Agent 平台（7 种终端后端、6 个消息平台、200+ 模型）。YINYO 是飞书这个垂直场景的精品——只做好一件事，用论文前沿的记忆架构 + LLM 驱动的工程纪律，做出 Hermes 做不到的飞书深度体验。

| 维度 | Hermes | YINYO |
|------|:--:|:--:|
| 飞书原生 | ❌ | ✅ 12 项全绿 |
| DeepSeek 1M 上下文利用 | ❌（通用适配） | ✅ 深度利用 |
| Dual-Process 记忆 | ❌（Honcho） | ✅ 三篇 2026 论文融合 |
| AHE 工程纪律 | ❌ | ✅ 盲测 + Manifest |
| 多平台网关 | ✅ Telegram/DC/Slack… | ❌ 只有飞书 |
| TUI | ✅ 完整终端界面 | ❌ 飞书即界面 |
| 测试规模 | 3,289 | 57 |
| 社区生态 | 167K ★ | 🆕 |

---

## 架构

```
用户消息（飞书）
        │
        ▼
┌──────────────────────────────────────────┐
│   Session Manager    去重、命令路由、对话历史   │
└────────────────────┬─────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────┐
│   YinyoAgent.run()    核心循环入口          │
│                                            │
│   ┌──────────────────────────────────┐    │
│   │         ReAct 循环（≤50 步）       │    │
│   │  ┌──────────┐    ┌────────────┐   │    │
│   │  │  Model   │───▶│ Tool Calls │   │    │
│   │  │ Gateway  │◀───│ (并行 10)  │   │    │
│   │  └──────────┘    └─────┬──────┘   │    │
│   │                        │           │    │
│   │  ┌─────────────────────▼───────┐   │    │
│   │  │  证据链 + 验证              │   │    │
│   │  └─────────────────────────────┘   │    │
│   └──────────────────────────────────┘    │
│                                            │
│   ┌──────────────────────────────────┐    │
│   │  自动反思 → Dual-Process 记忆更新 │    │
│   │  深度反思（每 10 次）             │    │
│   └──────────────────────────────────┘    │
└──────────────────────────────────────────┘
```

---

## 核心组件

| 组件 | 文件 | 职责 |
|------|------|------|
| Agent 循环 | `yinyo/agent.py` | ReAct + Plan + Reflect + Auto-Manifest |
| 模型网关 | `yinyo/model.py` | DeepSeek API + 跨 provider fallback + Mock |
| 记忆系统 | `yinyo/memory.py` | Dual-Process + TemporalTree + VectorCache |
| 记忆工具 | `yinyo/memory_tool.py` | USER.md / MEMORY.md 增删改 |
| 工具注册 | `yinyo/tools.py` | 10 个原子工具注册与调度 |
| 上下文管理 | `yinyo/context.py` | LLM 压缩 + DAG 归档 + 语义检索 |
| 视觉适配 | `yinyo/vision_adapter.py` | 外部视觉模型→文本注入 |
| 子 Agent | `yinyo/delegate.py` | 监督者-工人并行执行 |
| 进化引擎 | `yinyo/evolution.py` | Trace2Skill + Change Manifest + 自检 |
| 飞书适配 | `yinyo/feishu_adapter.py` | 消息解析、图片检测、会话路由 |
| 证据链 | `yinyo/evidence.py` | 哈希存证工具调用 |
| 风险治理 | `yinyo/governance.py` | 风险策略引擎 |

**总计：16 个 .py 文件，约 5,000 行纯 Agent 逻辑。**

---

## 版本历史

| 版本 | 日期 | 关键变更 | 盲测通过率 |
|------|------|----------|:----------:|
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
| [SOUL.md](yinyo/SOUL.md) | Agent 身份与人格（隐曜） |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 贡献指南 + 盲测流程 |
| [SECURITY.md](SECURITY.md) | 安全策略与信任模型 |
| [spec/](spec/) | 8 个版本 Spec（v2.1 → v8.1） |

---

## 设计原则

1. **Less is more** — 毙掉 10+ 非核心功能。每个功能必须有存在价值。只做飞书。
2. **集百家之长** — 每个设计背后都有论文或一线 Agent 实践支撑。不拍脑袋。
3. **DeepSeek 深度适配** — 1M 上下文充分利用。token 便宜到可以保留对话全貌。能用 LLM 的不用规则引擎。

---

## 贡献

欢迎提交 Issue 和 PR。详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

开发快速开始：

```bash
git clone https://github.com/xiaoshiyilangzhao1996-droid/yinyo.git
cd yinyo
pip install -e ".[dev]"
pytest tests/ -v
```

---

## 社区

- 🐛 [GitHub Issues](https://github.com/xiaoshiyilangzhao1996-droid/yinyo/issues)

---

## 许可证

MIT © 2026 Yinyo Contributors
