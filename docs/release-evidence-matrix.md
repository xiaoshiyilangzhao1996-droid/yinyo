<div align="center">

# Release Evidence Matrix

"Every product claim needs a proof path."

![Scope](https://img.shields.io/badge/scope-evidence-blue)
![Version](https://img.shields.io/badge/version-1.0.0--lite-2ea043)
![Gate](https://img.shields.io/badge/1.0-live%20bundle%20required-d73a49)

</div>

This page is the public index for YINYO's 3+6 product evidence, ETCLOVG
harness-layer evidence, and the live Feishu records required before full
`1.0.0`.

[3+6 Matrix](#36-matrix) · [ETCLOVG](#etclovg) · [Survey Anchor](#survey-anchor) · [Release Use](#release-use)

---

## 3+6 Matrix

The authoritative executable mapping lives in `yinyo/release_matrix.py`.
`python scripts/replay_scenarios.py --matrix` evaluates this table against the
versioned harness corpus in `corpus/harness/scenarios.v1.json`.

| Claim | Local scenarios | Required proof | Live `1.0.0` evidence |
|---|---|---|---|
| Less is more | `text_reply`, `duplicate_text`, `ws_sdk_envelope_normalization` | `gateway_job`, `duplicate_guard`, `ws_sdk_envelope` | `text_message_reply`, `duplicate_callback` |
| Borrow what works | `memory_supersession`, `memory_durability_policy`, `temporal_state_recovery`, `trace2skill_promotion` | `memory_supersession`, `memory_durability`, `temporal_state_recovery`, `trace2skill_regression` | `memory_supersession`, `trace2skill_promotion` |
| DeepSeek adapted | `deepseek_usage`, `partial_failure` | `model_usage`, `partial_failure` | `deepseek_usage`, `partial_failure` |
| Curiosity | `memory_supersession`, `memory_durability_policy`, `temporal_state_recovery` | durable fact filtering, supersession, recovery | `memory_supersession` |
| Reliability | `text_reply`, `image_understanding`, `ack_boundary`, `ws_sdk_envelope_normalization`, `card_fallback`, `duplicate_text` | gateway, image, ACK, SDK, fallback, duplicate proof | `text_message_reply`, `image_message_reply`, `ws_ack_boundary`, `card_fallback`, `duplicate_callback` |
| Fact hygiene | `memory_supersession`, `fact_hygiene_policy`, `partial_failure` | source-required answers, redacted partial-failure proof | `memory_supersession`, `partial_failure` |
| Multidisciplinary thinking | `image_understanding`, `long_conversation`, `trace2skill_promotion` | image, long-context, Trace2Skill regression proof | `image_understanding`, `long_conversation`, `trace2skill_promotion` |
| Negative capability | `partial_failure` | user-visible partial status and operator evidence | `partial_failure` |
| Low ego, high drive | `state_handoff`, `release_gate` | replayable handoff and release blocker proof | verified ws bundle |

---

## ETCLOVG

YINYO uses ETCLOVG as a coverage checklist for harness engineering, not as a
marketing label.

| Layer | Required public proof |
|---|---|
| Execution | ACK boundary, SDK envelope normalization, bounded workers, runtime lock, workspace boundary, resource quotas |
| Tooling | typed tool wrappers, delegated worker traces, card fallback, partial failure |
| Context | long-context retention, TemporalTree supersession/recovery, source-required answers |
| Lifecycle | gateway jobs, Trace2Skill promotion, state handoff, release gate |
| Observability | runtime/job/smoke JSONL, model usage, diagnostics, failure diagnosis, handoff records |
| Verification | scenario replay, proof envelopes, bundle verifier, release gate, proof ablation |
| Governance | secret scan, confirmation metadata, redacted bundles, unsupported release blockers |

---

## Survey Anchor

The survey reference used by YINYO is the Agent Harness Engineering page at
`https://picrew.github.io/LLM-Harness/`, read as of 2026-05-29. The local
definition frozen for this repository is:

- Harnesses are an independent engineering layer around agentic LLM systems.
- ETCLOVG means Execution, Tooling, Context, Lifecycle, Observability,
  Verification, and Governance.
- The open-problem pressure YINYO tracks is execution hardening, reliable
  long-running state, trace-native diagnosis, standard handoffs, and adaptive
  simplification.

If the external page changes, YINYO's current release gate follows this local
definition until `docs/spec.md`, `yinyo/release_matrix.py`, and tests are
updated together.

---

## Release Use

`v1.0.0-lite` can ship with local matrix proof plus a clear live-evidence
boundary. Full `1.0.0` additionally requires:

- verified `transport=ws` redacted smoke bundle;
- live basic records for text, image, card fallback, duplicate callback, and
  ACK boundary;
- live advanced records for image understanding, long conversation, memory
  supersession, Trace2Skill promotion, DeepSeek usage, and partial failure;
- at least one replayable run-level `handoff.json`;
- `yinyo.live_provenance.v1` with non-placeholder attestation, Feishu app hash,
  tenant hash, and ws SDK session id.

