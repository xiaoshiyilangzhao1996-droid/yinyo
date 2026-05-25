# Changelog

All notable changes to YINYO (隐曜) will be documented in this file.

---

## [v7.0] — 2026-05-25

### Added
- **LLM Structured Compression**: Context compression upgraded from keyword extraction to LLM-driven structured summaries (ACON-inspired). `context.py` now uses `_llm_compress()` with JSON output format: `{decisions, files_changed, errors, state}`.
- **Auto-Reflect**: `_reflect_on_run()` in `agent.py` — after every run, the LLM reviews what happened and decides what to remember. Auto-updates MEMORY.md via memory_add/replace/remove.
- **Deep-Reflect**: `_deep_reflect()` in `agent.py` — every 10 runs, scans recent reflections for patterns, anti-patterns, and user trends.
- **AGENTS.md**: Development constitution — verified-before-trust, spec=code, blind audit, product perspective, pixel-level style precision.

### Changed
- `context.py`: max_tokens 25K → 50K (full 128K window utilization), keep_tail 32 → 64.
- `context.py`: Observation masking threshold 70% → 80%, LLM compression threshold 85% → 90%.
- `context.py`: `_keyword_compress()` refactored as fallback-only.

---

## [v6.0] — 2026-05-24

### Added
- **memory_tool.py** (~170 lines): USER.md/MEMORY.md CRUD operations. § delimiter format (Hermes-compatible). Dedup via first-80-char similarity. Auto-merge on overflow.
- **do_memory tool**: 8th atomic tool. Agent can self-manage memory via tool-calling.
- **Cognitive layer injection**: USER.md (1500 chars), MEMORY.md (2200 chars), AGENTS.md (1500 chars) injected into system prompt.
- **USER.md / MEMORY.md templates**: Auto-created on agent init.

### Changed
- `agent.py`: +40 lines injection logic. Search order: AGENTS.md → .yinyo.md.
- `tools.py`: +40 lines do_memory + registry.
- `__init__.py`: +10 lines exports.

---

## [v5.0] — 2026-05-23

### Added
- **feishu_adapter.py** (372 lines): Message parsing, session routing, Feishu event handling.
- **feishu_card.py** (77 lines): Card 2.0 JSON builder.
- **feishu_format.py** (201 lines): Markdown-to-Feishu format converter. Long message segmentation, title degradation, anti-truncation.
- **session.py** (156 lines): Per-user/chat session state management.

### Changed
- `agent.py`: Refactored to message-driven entry (`handle_message()`).
- **Positioning corrected**: YINYO is an independent Feishu Agent product, not a Harness Agent runtime.

---

## [v4.0] — 2026-05-22

### Added
- **Parallel tool calls**: `model.py` +1 line enabling `parallel_tool_calls=True`.
- **Plan phase**: `agent.py` +20 lines — before ReAct loop, generates step-by-step plan. Uses THINK_HIGH mode.
- **VectorCache**: `memory.py` +100 lines — TF-IDF semantic retrieval for cross-run memory search.

---

## [v3.0] — 2026-05-21

### Changed
- **Code Agent → Pure ReAct**: Removed `sandbox.py`. Rewrote `agent.py` and `tools.py` for pure ReAct loop.
- **Result**: Blind test pass rate improved from 48.9% (v2.1) to 97.8% (v3.0).

### Removed
- `sandbox.py` — Code execution sandbox removed.

---

## [v2.1] — 2026-05-20

### Added
- Initial architecture: ReAct loop + Code Agent hybrid.
- Basic tools: read, write, search, execute.
- Model gateway with thinking mode support.
- Evidence ledger and verification gate.

---

## Version Numbering

YINYO follows **vX.Y** where:
- **X**: Major version — architectural change or new capability tier.
- **Y**: Minor version — feature addition or significant refinement.

Blind test pass rate is reported for every version from v2.1 onwards.
