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

# YINYO (隐曜) ☤

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/xiaoshiyilangzhao1996-droid/yinyo"><img src="https://img.shields.io/badge/Built%20by-Contributors-blueviolet?style=for-the-badge" alt="Built by Yinyo Contributors"></a>
  <a href="README.zh-CN.md"><img src="https://img.shields.io/badge/Lang-中文-red?style=for-the-badge" alt="中文"></a>
</p>

**A self-improving AI agent purpose-built for Feishu (Lark).** Not a CLI framework, not a chatbot wrapper — YINYO is a standalone agent product with a complete cognitive layer (SOUL, AGENTS, USER, MEMORY), a paper-backed Dual-Process + TemporalTree memory architecture, and an LLM-driven self-evolution engine.

Tightly integrated with DeepSeek (128K → 1M context, tokens so cheap you can afford to keep entire conversation histories uncompressed), and only targets Feishu — because doing one thing well beats doing everything poorly.

<table>
<tr><td width="180"><b>Feishu-Native</b></td><td>Card 2.0 messages, long-text segmentation, title degradation, anti-truncation. 12 Feishu UX items all green. Message sending, image parsing, session routing — works out of the box, not bolted on.</td></tr>
<tr><td><b>Paper-Backed Memory</b></td><td>Dual-Process (episodic preservation + semantic extraction) + TemporalTree (hierarchical timeline where facts <strong>evolve and supersede</strong> rather than just append) + multi-scope retrieval. Built on three 2026 papers (Mem0 ECAI 2025, Dual-Process arXiv:2605.17625, TiMem arXiv:2601.02845).</td></tr>
<tr><td><b>Reflects & Evolves</b></td><td>Auto-reflects after every run. Deep-reflects every 10 runs. Extracts reusable skills from repeated failures (Trace2Skill). AHE engineering layer: auto-generates Change Manifests after every run, marks them verified after blind tests pass, auto-rolls back on failure.</td></tr>
<tr><td><b>SubAgents That Share Context</b></td><td>Supervisor-worker pattern. Subagents share the full parent context (follows Cognition.ai's two principles). Blind test audits run entirely by subagents — development and testing strictly separated. Self-audited v2.1 got 48.9%; blind-audited v3.0+ has held 100% for 6 consecutive versions.</td></tr>
<tr><td><b>Sees Images</b></td><td>Auto-recognizes screenshots sent via Feishu. External vision model as an adapter — swappable anytime.</td></tr>
<tr><td><b>Graceful Fallback</b></td><td>Intra-provider: DeepSeek Flash → Pro. Cross-provider: DeepSeek → z.ai/GLM. No single point of failure.</td></tr>
<tr><td><b>Evidence-Grounded</b></td><td>Every tool call is hashed and ledgered. Verification gate. Run manifests. No fabricated confirmations. If it can't be <code>stat</code>'d, <code>curl</code>'d, or tested — it's not done.</td></tr>
</table>

---

## Quick Install

```bash
pip install yinyo-agent
```

### Environment

```bash
export DEEPSEEK_API_KEY="sk-..."    # Required
export VISION_API_KEY="sk-..."      # For Vision (optional)
export GLM_API_KEY="..."            # For cross-provider fallback (optional)
```

---

## Quick Start

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

### Quick Reference

| Action | Command |
|--------|---------|
| Handle Feishu message | `agent.handle_message(user_id, chat_id, text)` |
| Run a task | `agent.run("task description")` |
| Inspect memory | `agent.memory.pprint()` |
| Run tests | `pytest tests/ -v` |
| Check version | `python -c "from yinyo import __version__; print(__version__)"` |

---

## How We Differ From Hermes / OpenClaw

YINYO **doesn't compete with Hermes on the general agent market**. Hermes is a 167K-star aircraft carrier — 7 terminal backends, 6 messaging platforms, 200+ models. YINYO is a precision instrument for one platform: Feishu. We trade breadth for depth — paper-backed memory architecture + LLM-driven engineering discipline that Hermes can't match in the Feishu niche.

| Dimension | Hermes | YINYO |
|-----------|:--:|:--:|
| Feishu-native | ❌ | ✅ 12 UX items green |
| DeepSeek 1M context | ❌ (generic) | ✅ Deep integration |
| Dual-Process memory | ❌ (Honcho) | ✅ 3 × 2026 papers |
| AHE engineering | ❌ | ✅ Blind test + Manifest |
| Multi-platform gateway | ✅ Telegram/DC/Slack… | ❌ Feishu only |
| TUI | ✅ Full terminal UI | ❌ Feishu is the UI |
| Test suite | 3,289 | 57 |
| Community | 167K ★ | 🆕 |

---

## Architecture

```
User Message (Feishu)
        │
        ▼
┌──────────────────────────────────────────┐
│   Session Manager    Dedup, routing, history │
└────────────────────┬─────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────┐
│   YinyoAgent.run()    Core loop entry       │
│                                            │
│   ┌──────────────────────────────────┐    │
│   │     ReAct Loop (≤50 steps)       │    │
│   │  ┌──────────┐    ┌────────────┐   │    │
│   │  │  Model   │───▶│ Tool Calls │   │    │
│   │  │ Gateway  │◀───│ (10 parallel)│   │    │
│   │  └──────────┘    └─────┬──────┘   │    │
│   │                        │           │    │
│   │  ┌─────────────────────▼───────┐   │    │
│   │  │  Evidence + Verification    │   │    │
│   │  └─────────────────────────────┘   │    │
│   └──────────────────────────────────┘    │
│                                            │
│   ┌──────────────────────────────────┐    │
│   │  Auto-Reflect → Dual-Process     │    │
│   │  Deep-Reflect (every 10 runs)    │    │
│   └──────────────────────────────────┘    │
└──────────────────────────────────────────┘
```

---

## Core Components

| Component | File | Role |
|-----------|------|------|
| Agent Loop | `yinyo/agent.py` | ReAct + Plan + Reflect + Auto-Manifest |
| Model Gateway | `yinyo/model.py` | DeepSeek API + cross-provider fallback + Mock |
| Memory System | `yinyo/memory.py` | Dual-Process + TemporalTree + VectorCache |
| Memory Tool | `yinyo/memory_tool.py` | USER.md / MEMORY.md CRUD |
| Tools Registry | `yinyo/tools.py` | 10 atomic tools + dispatch |
| Context Manager | `yinyo/context.py` | LLM compression + DAG archive + semantic retrieval |
| Vision Adapter | `yinyo/vision_adapter.py` | External vision → text injection |
| SubAgent | `yinyo/delegate.py` | Supervisor-worker parallel execution |
| Evolution Engine | `yinyo/evolution.py` | Trace2Skill + Change Manifest + self-check |
| Feishu Adapter | `yinyo/feishu_adapter.py` | Message parsing, image detection, session routing |
| Evidence | `yinyo/evidence.py` | Hashed tool ledger |
| Governance | `yinyo/governance.py` | Risk policy engine |

**Total: 16 .py files, ~5,000 lines of pure agent logic.**

---

## Version History

| Version | Date | Highlights | Blind Pass |
|---------|------|-----------|:----------:|
| v8.1 | 2026-05-25 | AHE engineering layer, 57-test suite, programmable mock | 100% |
| v8.0 | 2026-05-25 | Dual-Process memory, Vision, SubAgent, Provider Chain, Trace2Skill | 100% |
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
| [SOUL.md](yinyo/SOUL.md) | Agent personality and identity (隐曜) |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contribution guide + blind test workflow |
| [SECURITY.md](SECURITY.md) | Security policy and trust model |
| [spec/](spec/) | 8 version specs (v2.1 → v8.1) |

---

## Design Principles

1. **Less is more** — Kill 10+ non-core features. Every feature must prove its value. Feishu only.
2. **Stand on giants' shoulders** — Every design backed by papers or proven agent practice. No gut feelings.
3. **DeepSeek-first** — 1M context fully utilized. Tokens cheap enough to keep full conversations. LLM over rules.

---

## Contributing

Issues and PRs welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

Quick dev start:

```bash
git clone https://github.com/xiaoshiyilangzhao1996-droid/yinyo.git
cd yinyo
pip install -e ".[dev]"
pytest tests/ -v
```

---

## Community

- 🐛 [GitHub Issues](https://github.com/xiaoshiyilangzhao1996-droid/yinyo/issues)

---

## License

MIT © 2026 Zhengyuan Wang (Yinyo Contributors)
