# Changelog

All notable changes to YINYO (隐曜) will be documented in this file.

---

## [v8.1] — 2026-05-25

### Added
- **AHE-inspired Engineering Layer**: `_auto_manifest()` generates LLM-powered Change Manifests after each run (~$0.0003). `verify_manifest()` auto-updates status to verified/reverted after blind test.
- **ChangeManifest upgrade**: Structured manifests with `status`/`verdict`/`blind_test` fields, `get_latest_verified_run()` for rollback, `list_manifests()` for querying.
- **Comprehensive Test Suite**: 57 tests (17 memory + 8 model + 12 tools + 8 agent + 12 edge cases). Mock-based, zero external API dependency.
- **Programmable mock**: `model.set_mock_responses()` for deterministic ReAct loop testing.

### Changed
- `evolution.py`: ChangeManifest upgraded with structured manifest lifecycle (draft → verified/reverted).
- `agent.py`: +87 lines (_auto_manifest + verify_manifest methods).
- `tests/`: 7 new test files with shared conftest.py fixtures.

---

## [v8.0] — 2026-05-25

### Added
- **Dual-Process + TemporalTree Memory**: Fusion of Dual-Process (arXiv:2605.17625) + TiMem temporal tree (arXiv:2601.02845) + Mem0 Multi-Scope. Facts evolve through lifecycle: created → confirmed → superseded → archived.
- **vision_adapter.py** (~120 lines): External vision model adapter (GPT-4o-mini Vision). New `do_vision` tool.
- **delegate.py** (~200 lines): Supervisor-Worker subagent pattern with full context sharing. New `delegate_task` tool.
- **Provider Chain**: `model.py` supports cross-provider fallback (DeepSeek Flash → Pro → GLM).
- **Trace2Skill**: `SkillEvolution` class — failure detection → LLM skill extraction → auto-loading → cross-session fusion.
- **Feishu image handling**: Auto-detect image messages, download, call do_vision, inject text description.
- **FactExtractor**: LLM-powered fact extraction from conversations, stored in TemporalTree.

### Changed
- `memory.py`: Complete rewrite (213 → 450 lines). TemporalTree with supersede mechanism, FactExtractor.
- `memory_tool.py`: +80 lines (Multi-Scope, supersede, audit operations). MEMORY_LIMIT 2,200 → 10,000.
- `model.py`: +50 lines (provider_chain with `_build_provider_chain()`).
- `evolution.py`: +150 lines (SkillEvolution class).
- `tools.py`: +60 lines (do_vision + delegate_task registrations, `execute()` method). Tools: 8 → 10.
- `agent.py`: +60 lines (skill auto-load, memory model injection, provider chain integration).
- `feishu_adapter.py`: +90 lines (image message detection + download + vision pipeline).
- Total: ~2,900 → ~5,200 lines. 14 → 16 .py files.

### References
- Dual-Process Memory: arXiv:2605.17625 (May 2026)
- TiMem Temporal Memory Tree: arXiv:2601.02845
- Mem0 Multi-Scope: ECAI 2025 (92.5 LoCoMo)
- Cognition.ai "Don't Build Multi-Agents" (context sharing principles)
- Trace2Skill: AHE self-evolution concept

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
