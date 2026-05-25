# Contributing to YINYO

Thank you for your interest in contributing to YINYO (隐曜)!

This guide covers the development workflow, code standards, and contribution priorities.

---

## Contribution Priorities

We value contributions in this order:

1. **Bug fixes** — crashes, incorrect behavior, memory corruption. Always top priority.
2. **Feishu compatibility** — new Feishu API versions, message format changes, Card 2.0 improvements.
3. **Security hardening** — prompt injection, path traversal, credential leaks. See [SECURITY.md](SECURITY.md).
4. **DeepSeek optimization** — context caching, parallel tool calls, token efficiency.
5. **New tools** — sparingly. YINYO's philosophy is minimal tool surface. Most capabilities should be YAML skills, not hardcoded tools.
6. **Documentation** — fixes, clarifications, new examples.
7. **Tests** — expanding the blind test suite.

---

## Development Setup

### Prerequisites

| Requirement | Notes |
|-------------|-------|
| Python 3.11+ | Core runtime |
| DeepSeek API key | `DEEPSEEK_API_KEY` env var |
| Feishu app credentials | For integration testing (optional) |

### Setup

```bash
git clone https://github.com/xiaoshiyilangzhao1996-droid/yinyo.git
cd yinyo
pip install -e ".[dev]"
```

### Run Tests

```bash
# Blind test suite (recommended)
python tests/run_blind_test.py

# Unit tests
pytest tests/ -v
```

---

## Architecture

YINYO is a **single-package Python library**. The core loop is in `agent.py`:

```
YinyoAgent
├── run(task)          # Core ReAct + Plan + Reflect loop
├── handle_message()   # Feishu message entry point
├── _reflect_on_run()  # Post-run LLM reflection
└── _deep_reflect()    # Periodic cross-run pattern analysis
```

### Key Design Decisions

1. **Pure ReAct, no Code Agent** — v3.0 removed the sandbox. All tool calls go through the loop.
2. **LLM for everything** — compression, reflection, memory management all use LLM (not rules). DeepSeek V4 is cheap enough.
3. **File-system memory** — no vector databases. MEMORY.md is the source of truth. VectorCache is TF-IDF for search.
4. **Feishu-first** — message format, session management, Card 2.0 are first-class.

---

## Adding a Tool

Tools are registered in `tools.py`:

```python
from tools import tool, registry

@tool(permission="ALLOW")
def my_tool(param: str) -> dict:
    """Tool description for the LLM."""
    # implementation
    return {"result": "..."}

# Auto-registered via decorator
```

Tools must:
- Be idempotent or clearly state side effects
- Return JSON-serializable results
- Include error handling (never crash the agent loop)
- Document permission level (ALLOW / ASK / DENY)

---

## Adding a YAML Skill

Skills live in `{workspace}/skills/{hash}/SKILL.md` with optional `tools.yaml`:

```yaml
# tools.yaml
tools:
  - name: my_custom_tool
    description: What this tool does
    command: python scripts/my_script.py {param}
    parameters:
      param:
        type: string
        description: Parameter description
```

---

## Code Standards

- **Python 3.11+** with type hints.
- **Max 500 lines per file** — if a file grows beyond this, split it.
- **Docstrings required** for all public functions.
- **Evidence-first**: every tool call result must be hashable and verifiable.
- **Blind test pass**: all changes must pass the blind test suite (independent agent audit).

### Commit Messages

```
type: Short description (max 72 chars)

- Detailed bullet points
- What changed and why

Version: vX.Y
Pass Rate: XX%
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`

---

## Blind Test Requirement

YINYO uses **blind testing** — an independent sub-agent audits the code without seeing the source:

1. Write code + update spec.
2. Delegate blind test to independent sub-agent: "Here is the CLI usage and test suite. Run all 12 tests. Do NOT read the source code."
3. Fix all failures.
4. Re-run blind test until 100%.

This is non-negotiable. v2.1 failed because we skipped it (48.9%). v3.0+ is 100% because we didn't.

---

## Questions?

Open an issue or discussion on GitHub.
