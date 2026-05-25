# YINYO Architecture

## Overview

YINYO is a **single-package Python library** implementing an autonomous agent for Feishu. The architecture follows a layered design:

```
┌──────────────────────────────────────────┐
│              Entry Points                │
│  handle_message()    /    run()          │
└────────────────┬─────────────────────────┘
                 │
┌────────────────▼─────────────────────────┐
│           Session Manager               │
│  Dedup, command routing, history         │
└────────────────┬─────────────────────────┘
                 │
┌────────────────▼─────────────────────────┐
│              Agent Loop                  │
│  ┌──────────────────────────────────┐    │
│  │  Plan Phase (optional)           │    │
│  │  - Generate step-by-step plan    │    │
│  │  - THINK_HIGH mode              │    │
│  └──────────────┬───────────────────┘    │
│                 ▼                        │
│  ┌──────────────────────────────────┐    │
│  │  ReAct Loop (max 50 steps)       │    │
│  │  ┌────────┐     ┌────────────┐   │    │
│  │  │ Model  │────▶│ Tool Calls │   │    │
│  │  │Gateway │◀────│ (parallel) │   │    │
│  │  └────────┘     └─────┬──────┘   │    │
│  │                       │          │    │
│  │  ┌────────────────────▼───────┐  │    │
│  │  │  Evidence + Verification   │  │    │
│  │  │  - Hash tool results       │  │    │
│  │  │  - Verify integrity        │  │    │
│  │  │  - Governance check        │  │    │
│  │  └────────────────────────────┘  │    │
│  └──────────────────────────────────┘    │
└────────────────┬─────────────────────────┘
                 │
┌────────────────▼─────────────────────────┐
│           Reflection Layer               │
│  ┌──────────────────────────────────┐    │
│  │  Auto-Reflect (every run)        │    │
│  │  - Review task + result          │    │
│  │  - Auto-update MEMORY.md         │    │
│  │  - Write reflection.md           │    │
│  └──────────────────────────────────┘    │
│  ┌──────────────────────────────────┐    │
│  │  Deep-Reflect (every 10 runs)    │    │
│  │  - Scan recent reflections       │    │
│  │  - Detect patterns/anti-patterns │    │
│  │  - Update MEMORY.md trends       │    │
│  └──────────────────────────────────┘    │
└──────────────────────────────────────────┘
```

---

## Core Components

### 1. Agent Loop (`agent.py`)

The central orchestrator. Implements:
- **Plan phase**: Before execution, generates a step-by-step plan using THINK_HIGH mode.
- **ReAct loop**: Iterates between model reasoning and tool execution. Supports parallel tool calls.
- **Auto-reflect**: After each run, LLM reviews and decides what to remember.
- **Deep-reflect**: Every 10 runs, cross-run pattern analysis.

### 2. Context Manager (`context.py`)

Three-layer context management:
1. **Observation Masking** (token > 80%): Hide older tool outputs.
2. **LLM DAG Compression** (token > 90%): LLM generates structured summaries (ACON-inspired).
3. **Memory Retrieval**: Semantic search via VectorCache (TF-IDF).

### 3. Memory System

Two-tier architecture:

| Tier | Storage | Purpose |
|------|---------|---------|
| **Inject** | USER.md + MEMORY.md | Injected into system prompt every run |
| **Retrieve** | VectorCache (TF-IDF) | Semantic search for relevant past memories |

**Memory Tool** (`memory_tool.py`): CRUD operations with:
- § delimiter format (Hermes-compatible)
- Dedup via first-80-char similarity
- Auto-merge on overflow
- Substring matching for replace/remove

### 4. Model Gateway (`model.py`)

DeepSeek API wrapper with:
- Three thinking modes: NON_THINK, THINK_HIGH, THINK_MAX
- Auto-fallback to deepseek-v4-pro on errors
- Parallel tool call support (`parallel_tool_calls=True`)

### 5. Tools (`tools.py`)

8 atomic tools registered via decorator:

| Tool | Permission | Description |
|------|-----------|-------------|
| `read` | ALLOW | Read files with pagination |
| `write` | ASK | Write/overwrite files |
| `patch` | ALLOW | Targeted find-and-replace |
| `search` | ALLOW | Regex search in files |
| `execute` | ASK | Run Python code |
| `web` | ALLOW | Web search (Tavily) |
| `web_think` | ALLOW | Web search + deep analysis |
| `do_memory` | ALLOW | Manage USER.md/MEMORY.md |

YAML tools can be loaded from `{workspace}/skills/*/tools.yaml`.

### 6. Feishu Integration

| Component | Lines | Role |
|-----------|-------|------|
| `feishu_adapter.py` | 372 | Message parsing, event handling, session routing |
| `feishu_card.py` | 77 | Card 2.0 JSON builder |
| `feishu_format.py` | 201 | Markdown → Feishu format, long message segmentation, anti-truncation |
| `session.py` | 156 | Per-user/chat session state |

### 7. Evidence & Governance

- **Evidence Ledger**: Every tool call hashed and logged to `runs/{run_id}/evidence.jsonl`.
- **Verification Gate**: Checks tool results for integrity.
- **Governance Policy**: Risk-based blocking of dangerous operations.

---

## Data Flow

```
User Message
  │
  ├─ Session Manager: dedup, command routing
  │
  ├─ Agent.run(task):
  │   ├─ Load SOUL.md + USER.md + MEMORY.md + AGENTS.md → system prompt
  │   ├─ Plan phase: generate step plan
  │   ├─ ReAct loop:
  │   │   ├─ Model.chat(messages, tools)
  │   │   ├─ Execute tool calls (parallel)
  │   │   ├─ Evidence ledger: hash + log
  │   │   ├─ Verification gate: integrity check
  │   │   └─ Auto-manage context (masking/compression)
  │   ├─ Auto-reflect: LLM reviews → update MEMORY.md
  │   └─ Deep-reflect (every 10 runs): pattern analysis
  │
  └─ Return result → Feishu format → Send
```

---

## Design Decisions

### Why Pure ReAct (no Code Agent)?
v3.0 removed the Code Agent sandbox. Pure ReAct is simpler, more transparent, and aligns with how frontier agents (Claude Code, Codex CLI) work. The model decides what tools to call — no intermediate code generation layer.

### Why File-System Memory (no Vector DB)?
HERMES's own benchmarks (Letta) show file-system memory can outperform dedicated vector DBs (74% vs lower). Simpler to deploy, easier to debug, no external dependencies.

### Why LLM for Everything?
DeepSeek V4 costs ~$0.27/M tokens. LLM compression: ~$0.0003/run. Auto-reflect: ~$0.0005/run. Deep-reflect: ~$0.002/10 runs. Total cost per run: < $0.001. Cheaper than maintaining complex rule systems.

### Why Blind Testing?
The builder cannot verify their own work. v2.1 was self-reviewed → 48.9%. v3.0+ uses independent sub-agent blind audit → 100%. This is now encoded in AGENTS.md as a non-negotiable rule.
