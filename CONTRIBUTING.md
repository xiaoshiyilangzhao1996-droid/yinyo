# Contributing to YINYO

YINYO is a Feishu-first agent product. Contributions should strengthen the
runtime, evidence chain, packaging, or operator workflow without widening the
product beyond that boundary.

---

## Priorities

1. Release blockers: live smoke workflow, redaction, diagnostics, packaging,
   and release verification.
2. Feishu compatibility: long connection, HTTP fallback, message formats, and
   Card 2.0 behavior.
3. Reliability: idempotency, durable jobs, outbox behavior, evidence records,
   and failure states.
4. Security hardening: token handling, prompt-injection resistance, path safety,
   and secret scans.
5. Documentation: corrections that keep claims tied to source, tests, or live
   evidence.
6. New tools: only when they fit the small audited tool surface.

---

## Setup

```bash
git clone https://github.com/xiaoshiyilangzhao1996-droid/yinyo.git
cd yinyo
python -m pip install -e ".[dev]"
```

Optional live testing requires a Feishu self-built app and model-provider keys.
Do not commit local config or raw evidence files.

---

## Checks

Run the focused checks for your change, then run the release-oriented local
suite before handing off broad changes:

```bash
python -m pytest tests -q
python scripts/replay_scenarios.py --matrix
python scripts/verify_release.py --json
python scripts/verify_secrets.py
python -m build
python scripts/verify_wheel.py --skip-build
```

For a `1.0.0` claim, the strict gate must pass with real live evidence or a
verified redacted bundle:

```bash
python scripts/verify_release.py --target 1.0.0 --bundle <bundle-dir> --candidate 1.0.0
```

If that command fails because live Feishu evidence is missing, report the
blocker. Do not weaken the verifier or create synthetic live records.

---

## Code Rules

- Keep changes small and test-backed.
- Preserve Feishu as the primary product surface.
- Keep HTTP webhook behavior tested, but do not replace the long-connection
  release proof path.
- Add or update acceptance checks in `docs/spec.md` for new product claims.
- Keep secrets out of source, docs, memory, logs, and shared artifacts.
- Use the controlled smoke and advanced evidence commands instead of editing
  JSONL evidence by hand.

---

## Architecture

The main runtime path is:

```text
Feishu event
  -> long connection or HTTP fallback
  -> runtime gateway
  -> durable idempotency
  -> runtime job
  -> YinyoAgent
  -> outbox reply
  -> runtime and smoke evidence
```

Core files:

| File | Role |
|---|---|
| `yinyo/service.py` | Service entry and runtime assembly. |
| `yinyo/feishu_ws.py` | Feishu long-connection transport. |
| `yinyo/feishu_adapter.py` | HTTP fallback and Feishu API boundary. |
| `yinyo/gateway.py` | Event verification, normalization, idempotency, and job dispatch. |
| `yinyo/smoke.py` | Live smoke records, evidence chains, bundles, and verification. |
| `scripts/verify_release.py` | Release readiness and final candidate gate. |

---

## Commit Hygiene

- Do not commit `.venv/`, build artifacts, local `workspace/`, raw `.env`, or
  unredacted runtime JSONL files.
- Keep public versioning SemVer-based; internal P-series gates are not release
  versions.
- Do not claim `1.0.0` readiness unless the strict candidate gate passes.
