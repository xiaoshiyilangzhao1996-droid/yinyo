<div align="center">

# YINYO Handoff

"Carry the product context across agent sessions."

![Status](https://img.shields.io/badge/status-lite-2ea043)
![Scope](https://img.shields.io/badge/scope-handoff-blue)
![Root](https://img.shields.io/badge/root-repo-2ea043)

</div>

Cross-session handoff for maintainers and future agents working on YINYO.

[Project Root](#project-root) · [Product Identity](#product-identity) · [Decision Record](#decision-record) · [Current Evidence](#current-evidence) · [Open Work](#open-work)

---

## Project Root

Work from the repository root checked out by the maintainer or tester:

```text
<repo>
```

Generated Codex session directories, exported chat logs, build outputs, virtual
environments, and live smoke workspaces are not the project truth. The
maintained product truth is the repository docs, tests, release gates, and
tracked source files.

---

## Product Identity

YINYO is a harness Agent product benchmarked against Hermes and OpenClaw. It is
not a generic chat-bot wrapper and not a broad multi-platform agent gateway.

The first product surface is Feishu plus DeepSeek:

- Feishu provides the concrete user and runtime surface.
- DeepSeek assumptions shape the model gateway, long-context behavior,
  fallback, retry, and usage telemetry.
- Local harness mechanisms must be proven by tests and scenario replay.
- Public `1.0.0` claims require live Feishu evidence or a verified redacted
  bundle.

The product constitution has three cores:

- Less is more.
- Borrow what works.
- DeepSeek adapted.

It also has six behavioral traits:

- Curiosity.
- Reliability.
- Fact hygiene.
- Multidisciplinary thinking.
- Negative capability.
- Low ego, high drive.

These are product constraints, not slogans. Each claim should map to executable
evidence in `docs/spec.md`, `yinyo/release_matrix.py`, tests, local scenario
replay, or live Feishu evidence.

---

## Decision Record

The earlier prototype had useful ideas but weak translation from vision to
SPEC. The retained direction is:

- Keep the vision and product constitution.
- Rewrite SPEC as acceptance gates rather than architecture prose.
- Reuse code where it can be made testable.
- Remove or downgrade unsupported public claims.
- Keep Feishu-only as the current product boundary.
- Keep local evidence and live evidence separate.

Important engineering decisions already made:

- A stable, standalone project checkout is required; do not develop from
  transient dated session directories.
- External versioning uses SemVer-style product versions.
- Internal `v8.x` history is prototype history only.
- `1.0.0` must not pass without real live Feishu evidence or a verified redacted
  bundle.
- Local scenario replay is necessary but not sufficient for public `1.0.0`.
- Advanced live evidence must be produced through supported smoke commands, not
  hand-edited JSONL.
- The 2026 Agent Harness Engineering survey is now an explicit reference for
  YINYO's harness framing: ETCLOVG is the architecture coverage checklist, and
  trace-native proof envelopes plus per-run `handoff.json` packets are executable
  release objects for proof and state transfer.

---

## Current Evidence

The current `1.0.0-lite` line has local product evidence for:

- Runtime gateway acceptance, idempotency, bounded jobs, outbox delivery, and
  diagnostics.
- DeepSeek-first model gateway behavior, retry/fallback, model usage, and
  partial failure states.
- TemporalTree memory supersession and memory durability filtering.
- Trace2Skill promotion and regression evidence.
- Long-context retention and source-required fact hygiene.
- Per-run structured handoff packets linked from run manifests.
- Release matrix mapping the 3 product cores and 6 behavioral traits to local
  checks.
- Secret scanning, build, wheel verification, and default release audit.

The latest verified local count in public docs is `353 local tests`. Re-run
`python -m pytest tests -q` in the project virtual environment before changing
that number.

The strict release guard is expected to fail until live evidence exists:

```bash
python scripts/verify_release.py --target 1.0.0 --candidate 1.0.0 --json
```

That failure is a correct product boundary, not a bug, as long as the blockers
are missing live Feishu smoke, long-connection evidence, and advanced live
records.

---

## Open Work

The highest-value remaining local issue is making live evidence prove the same
trace, proof-envelope, and handoff chain that local fixtures now prove.

Recommended next local work:

- Extend bundle verification so shared release bundles can include handoff
  packets alongside runtime, job, event, smoke, and diagnostics evidence.
- Keep adding proof predicates when a new harness claim enters `docs/spec.md`.
- Require live run ids, manifests, evidence files, smoke records, bundle
  digests, and handoff records where release claims depend on them.

Recommended external release work:

- Run Feishu long-connection live smoke against a real app.
- Capture text, image, card fallback, and duplicate callback evidence.
- Capture advanced records for image understanding, long conversation, memory
  supersession, Trace2Skill promotion, DeepSeek usage, and partial failure.
- Bundle and verify redacted evidence before any `1.0.0` candidate.

---

## Read Order

Future agents should read these files in order:

1. `README.md`
2. `docs/handoff.md`
3. `docs/spec.md`
4. `AGENTS.md`
5. `MAINTENANCE.md`
6. `docs/deployment.md`
7. `SECURITY.md`
