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

The three product cores are Less is more, Borrow what works, and DeepSeek adapted.
The six behavioral traits are Curiosity, Reliability, Fact hygiene,
Multidisciplinary thinking, Negative capability, and Low ego, high drive.

The authoritative executable mapping lives in `yinyo/release_matrix.py`.
`python scripts/replay_scenarios.py --matrix` evaluates this table against the
versioned harness corpus in `corpus/harness/scenarios.v1.json`.

| ID | Claim | Local scenarios | Required proof | Live `1.0.0` evidence |
|---|---|---|---|---|
| `core.less_is_more` | Feishu-only service boundary | `text_reply`, `duplicate_text`, `ws_sdk_envelope_normalization` | `gateway_job`, `duplicate_guard`, `ws_sdk_envelope` | `text_message_reply`, `duplicate_callback` |
| `core.borrow_what_works` | Memory/evolution mechanisms improve workflows | `memory_supersession`, `memory_durability_policy`, `temporal_state_recovery`, `trace2skill_promotion` | `memory_supersession`, `memory_durability`, `temporal_state_recovery`, `trace2skill_regression` | `memory_supersession`, `trace2skill_promotion` |
| `core.deepseek_adapted` | DeepSeek usage and degradation are measured | `deepseek_usage`, `partial_failure` | `model_usage`, `partial_failure` | `deepseek_usage`, `partial_failure` |
| `trait.curiosity` | Reflection stores durable facts only | `memory_supersession`, `memory_durability_policy`, `temporal_state_recovery` | `memory_supersession`, `memory_durability`, `temporal_state_recovery` | `memory_supersession` |
| `trait.reliability` | Evidence-backed runtime delivery | `text_reply`, `image_understanding`, `ack_boundary`, `ws_sdk_envelope_normalization`, `card_fallback`, `duplicate_text` | `gateway_job`, `image_understanding`, `ack_boundary`, `ws_sdk_envelope`, `card_fallback`, `duplicate_guard` | `text_message_reply`, `image_message_reply`, `ws_ack_boundary`, `card_fallback`, `duplicate_callback` |
| `trait.fact_hygiene` | Facts and shared evidence are source-bound and redacted | `memory_supersession`, `fact_hygiene_policy`, `partial_failure` | `memory_supersession`, `source_required`, `partial_failure` | `memory_supersession`, `partial_failure` |
| `trait.multidisciplinary` | Research mechanisms prove product value | `image_understanding`, `long_conversation`, `trace2skill_promotion` | `image_understanding`, `long_context`, `trace2skill_regression` | `image_understanding`, `long_conversation`, `trace2skill_promotion` |
| `trait.negative_capability` | Failures are explicit to users and operators | `partial_failure` | `partial_failure` | `partial_failure` |
| `trait.low_ego_high_drive` | Claims require replayable evidence and transferable state | `state_handoff`, `release_gate` | `state_handoff`, `release_gate` | `verified_ws_bundle` |

---

## ETCLOVG

YINYO uses ETCLOVG as a coverage checklist for harness engineering, not as a
marketing label.

| Layer | Claim | Required public proof |
|---|---|
| Execution | Feishu events execute through ACK, SDK envelope normalization, bounded workers, durable jobs, quotas, and delivery. | `gateway_job`, `ack_boundary`, `ws_sdk_envelope`, `worker_saturation`, `workspace_boundary`, `resource_quota`, `duplicate_guard`, `card_fallback`, `partial_failure` |
| Tooling | Tool use is governed by confirmation, delegated workers, and failure boundaries. | `card_fallback`, `delegated_worker_trace`, `partial_failure`, `state_handoff` |
| Context | Long context and memory are retained, masked, superseded, recovered, and source-bound. | `long_context`, `memory_supersession`, `memory_durability`, `temporal_state_recovery`, `source_required` |
| Lifecycle | Failures become replay-validated skills, delegated work traces, and release state transfers. | `trace2skill_regression`, `delegated_worker_trace`, `state_handoff`, `release_gate` |
| Observability | Runtime, model, failure, pressure, and handoff claims carry operator evidence. | `gateway_job`, `model_usage`, `worker_saturation`, `trace_failure_diagnosis`, `partial_failure`, `state_handoff` |
| Verification | Local harness claims are matrixed, envelope-backed, release-gated, SDK-envelope guarded, and ablation-guarded. | `release_gate`, `trace2skill_regression`, `trace_failure_diagnosis`, `ws_sdk_envelope`, `model_usage`, `adaptive_simplification` |
| Governance | Evidence, facts, secrets, runtime stores, workspaces, confirmations, and resource use remain bounded. | `source_required`, `memory_durability`, `temporal_state_recovery`, `runtime_lock`, `workspace_boundary`, `resource_quota`, `partial_failure`, `state_handoff` |

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
boundary. Full `1.0.0` additionally requires a verified ws bundle:

- verified `transport=ws` redacted smoke bundle;
- live basic records for text, image, card fallback, duplicate callback, and
  ACK boundary;
- live advanced records for image understanding, long conversation, memory
  supersession, Trace2Skill promotion, DeepSeek usage, and partial failure;
- at least one replayable run-level `handoff.json`;
- `yinyo.live_provenance.v1` with non-placeholder attestation, Feishu app hash,
  tenant hash, and ws SDK session id.
