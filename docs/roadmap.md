# Roadmap

This document tracks the gap between the current `1.0.0-lite` public line and a product that can be released as full `1.0.0`.

---

## Snapshot

| Area | Status |
|---|---|
| Validation | 356 local tests |
| Release gate | `1.0.0-lite` gate passes locally; strict full `1.0.0` gate blocks on live Feishu evidence. |
| Canonical root | Stable standalone repository checkout, not a dated session directory. |

---

## Current State

- Runtime Gateway is Feishu-native, with official long-connection transport by default and HTTP webhook as fallback.
- Long-connection ACK latency is observable and gated under the 3-second Feishu deadline.
- Trace2Skill, blind-test records, fallback, gateway idempotency, retention, memory supersession, card fallback, partial failure, and release blocking have local tests.
- The 2026 Agent Harness Engineering survey names ETCLOVG as the production harness layer split: Execution, Tooling, Context, Lifecycle, Observability, Verification, and Governance.
- YINYO maps local surfaces to those layers, writes trace-native proof envelopes, enforces a DeepSeek model envelope, emits per-run handoff packets for state transfer, and binds high-value local scenarios to the versioned harness corpus.
- Live bundles still need to prove the same trace, model, handoff, ACK, runtime, job, event-store, and advanced workflow chain with real Feishu evidence.

---

## 1.0 Blockers

| Area | Remaining work |
|---|---|
| Live Feishu smoke | Redacted ws evidence bundle for text, image, card fallback, duplicate callback, and long-connection runtime events. |
| Advanced workflows | Live Feishu records for image understanding, long conversation, memory supersession, Trace2Skill promotion, DeepSeek usage, and partial failure. |
| Release artifact | Verified bundle must pass `python scripts/verify_release.py --target 1.0.0 --bundle <dir> --candidate 1.0.0`. |

---

## Harness Survey Backlog

The 2026 Agent Harness Engineering survey turns five open problems into YINYO
backlog pressure after the 1.0 live gate:

| Survey problem | YINYO implication |
|---|---|
| Harden and scale execution environments | Worker-saturation, runtime-lock, workspace-boundary, and `yinyo.resource_quota.v1` scenarios are now in the versioned harness corpus; add OS/container sandbox proof before widening tool permissions. |
| Reliable state in long-running agents | `yinyo.temporal_state_report.v1` is proven locally and surfaced in `yinyo.frontier_readiness.v1`; live release still needs a real `memory_supersession` advanced record. |
| Trace-native failure diagnosis | `yinyo.trace_failure_diagnosis.v1` is emitted from diagnostics, proven by the corpus, and surfaced in live bundle triage. |
| Standard handoffs | `yinyo.handoff.v1` carries budget state and trace history through `replay_handoff()` and live bundle triage now marks missing run-level handoff packets as frontier blockers. |
| Adaptive simplification | `yinyo.proof_ablation.v1` proves the matrix fails when a load-bearing proof is removed, and `yinyo.frontier_readiness.v1` keeps that guard visible in live bundle triage before any harness layer, tool wrapper, verifier, or governance check is removed for cost or latency reasons. |

---

## Validation Commands

```bash
python scripts/replay_scenarios.py --matrix
python scripts/verify_release.py --json
python scripts/verify_secrets.py
python scripts/verify_wheel.py --skip-build
python -m pytest tests -q
```
