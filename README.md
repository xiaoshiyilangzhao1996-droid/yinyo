# YINYO (隐曜) — An Autonomous Feishu Agent That Learns

**YINYO** is a self-improving AI agent designed for **Feishu (Lark)**. It is not a CLI framework or a chatbot wrapper — it is an autonomous agent product with a complete cognitive layer (SOUL, AGENTS, USER, MEMORY), persistent memory that auto-reflects and deep-reflects, and DeepSeek-first design that exploits 128K context windows for LLM-driven everything.

> "The agent that speaks Feishu, thinks in DeepSeek, and learns from every conversation."

---

## Key Features

| Feature | Details |
|---------|---------|
| **Feishu-Native** | Card 2.0 messages, long-text segmentation, title degradation, anti-truncation. 12 Feishu UX items all green. |
| **ReAct + Plan Loop** | Pure ReAct loop with lightweight plan phase. Parallel tool calls. Max 50 steps. |
| **LLM-Driven Memory** | USER.md + MEMORY.md (injectable), VectorCache (TF-IDF semantic retrieval), auto-reflect after every run, deep-reflect every 10 runs. |
| **Self-Evolution** | Skill crystallization from repeat tool patterns. Change manifests. Self-checks on init. |
| **Evidence-Grounded** | Every tool call is hashed and ledgered. Verification gate. Run manifests. |
| **DeepSeek Optimized** | 128K context window fully utilized. LLM compression instead of rules. Context caching compatible. |
| **8 Atomic Tools** | read, write, patch, search, execute, web, web_think, do_memory — minimal surface, maximal power. |
| **Governance** | Risk policy engine. Blocked steps tracked. Thinking escalation on consecutive failures. |

---

## Quick Start

### Installation

```bash
pip install yinyo-agent
```

### Usage

```python
from yinyo import YinyoAgent

agent = YinyoAgent(workspace="./my_workspace")

# Handle a Feishu message
response = agent.handle_message(
    user_id="ou_xxx",
    chat_id="oc_xxx",
    text="帮我查一下最近 3 天的天气"
)

# Or run a task directly
result = agent.run("分析这份数据并生成报告")
```

### Environment

```bash
export DEEPSEEK_API_KEY="sk-..."
```

---

## Architecture

```
User Message (Feishu)
        │
        ▼
┌───────────────────┐
│  Session Manager  │  Dedup, command routing, conversation history
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│   YinyoAgent.run  │  Core loop entry
└────────┬──────────┘
         │
    ┌────▼────┐
    │  Plan   │  Lightweight step-by-step plan (optional)
    └────┬────┘
         │
    ┌────▼────────────────────────────────┐
    │           ReAct Loop                │
    │  ┌──────────┐    ┌──────────────┐   │
    │  │  Model   │───▶│ Tool Calls   │   │
    │  │ Gateway  │◀───│ (parallel)   │   │
    │  └──────────┘    └──────┬───────┘   │
    │                         │           │
    │  ┌──────────────────────▼────────┐  │
    │  │  Evidence + Verification      │  │
    │  └───────────────────────────────┘  │
    └─────────────────────────────────────┘
         │
    ┌────▼────────────────────┐
    │  Auto-Reflect + Memory  │
    │  Deep-Reflect (10 runs) │
    └─────────────────────────┘
```

## Core Components

| Component | File | Lines | Role |
|-----------|------|-------|------|
| Agent Loop | `agent.py` | 303 | ReAct + Plan + Reflect |
| Context Manager | `context.py` | 192 | LLM compression, masking, retrieval |
| Memory Store | `memory.py` | ~200 | Episodic + VectorCache |
| Memory Tool | `memory_tool.py` | ~170 | USER.md/MEMORY.md CRUD |
| Model Gateway | `model.py` | ~150 | DeepSeek API + thinking modes |
| Tools Registry | `tools.py` | ~200 | 8 tools + YAML loading |
| Feishu Adapter | `feishu_adapter.py` | 372 | Message parsing, session routing |
| Feishu Card | `feishu_card.py` | 77 | Card 2.0 builder |
| Feishu Format | `feishu_format.py` | 201 | Markdown → Feishu format |
| Session | `session.py` | 156 | Per-user/chat session state |
| Governance | `governance.py` | ~50 | Risk policy |
| Evidence | `evidence.py` | ~150 | Hashed tool ledger |
| Evolution | `evolution.py` | ~100 | Skill crystallizer, self-check |

**Total: ~2,700 lines of pure agent logic.**

---

## Version History

| Version | Date | Highlights | Pass Rate |
|---------|------|-----------|-----------|
| v7.0 | 2026-05-25 | LLM compression, auto/deep-reflect, AGENTS.md | 100% |
| v6.0 | 2026-05-24 | USER.md, MEMORY.md, do_memory tool | 100% |
| v5.0 | 2026-05-23 | Independent Feishu product, 12 Feishu UX items | 100% |
| v4.0 | 2026-05-22 | Parallel tool calls, Plan phase, VectorCache | 100% |
| v3.0 | 2026-05-21 | Code Agent → Pure ReAct | 97.8% |
| v2.1 | 2026-05-20 | Initial architecture | 48.9% |

See [CHANGELOG.md](CHANGELOG.md) for full details.

---

## Documentation

| Document | Content |
|----------|---------|
| [AGENTS.md](AGENTS.md) | Development constitution — rules, blood lessons, standards |
| [SOUL.md](yinyo/SOUL.md) | Agent personality and identity |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute |
| [SECURITY.md](SECURITY.md) | Security policy and trust model |
| [spec/](spec/) | Version change specifications |

---

## Design Principles

1. **Less is more** — Kill 10+ non-core features. Every feature must prove its value.
2. **Stand on giants' shoulders** — Every design backed by papers (ACON, Plan-and-Solve, CASS, Mem0) or proven agent practice.
3. **DeepSeek-first** — Exploit 128K context, parallel tool calls, ultra-low cost. Use LLM instead of rules everywhere.

---

## License

MIT © 2026 王正元 (Yinyo Contributors)
