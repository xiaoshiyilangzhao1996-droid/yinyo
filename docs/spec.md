# YINYO Acceptance Spec

This document is the development contract. The product vision stays in the
README; this file defines what must be true before a capability can be called
implemented.

---

## Product Constitution

YINYO keeps three product cores:

- Less is more: Feishu first, small tool surface, no general platform sprawl.
- Borrow what works: each research-inspired mechanism needs a testable behavior.
- DeepSeek adapted: large context, low-cost LLM calls, and tool calling are design
  assumptions with explicit fallback behavior.

YINYO keeps six behavioral traits:

- Curiosity: reflection records reusable facts, not empty praise.
- Reliability: no evidence means no success claim.
- Fact hygiene: code facts come from local execution; external facts need sources.
- Multidisciplinary thinking: research explains mechanisms but never replaces tests.
- Negative capability: timeout, empty response, and partial failure have clear states.
- Low ego, high drive: validation is separated from generation wherever practical.

---

## Frontier Mechanism Map

YINYO can use frontier research language only when the mechanism is tied to a
local acceptance check and a live Feishu evidence requirement.

| Mechanism | Inspiration | Claimed product advantage | Local acceptance evidence | Live evidence required for `1.0.0` |
|-----------|-------------|---------------------------|---------------------------|------------------------------------|
| TemporalTree memory | Temporal memory, supersession, state-report, and audit-trail practice | Durable user/project facts evolve with provenance, recovery, and stale-state diagnostics instead of stale facts piling up. | Memory supersession, durability filtering, state recovery report, search exclusion, provenance completeness, and audit-trail tests. | Live `memory_supersession` advanced record with redacted memory reference or run id. |
| Trace2Skill | Failure-driven skill extraction and regression replay | Repeated failures become guarded reusable procedures, not anecdotes. | Regression fixture, replay validation record, promotion record, failure trace ref, and post-promotion validation ref. | Live `trace2skill_promotion` advanced record with failure trace, promoted skill, validation result, promotion status, and post-promotion run references. |
| Long-context retention | Context compression and protected recent-context practice | Long conversations preserve recent/high-value context while masking old observations. | Retention report with token estimate, masked observations, compression count, and protected-tail check. | Live `long_conversation` advanced record with redacted transcript or run id. |
| DeepSeek adaptation | Low-cost large-context model use with observable fallback | Model behavior is measured through token/cost telemetry, budget envelope, retry, fallback, and explicit degradation. | `deepseek_usage` model envelope with token/cost budget, retry recovery, fallback attempts, model-error classification, and partial-failure tests. | Live `deepseek_usage` advanced record with usage reference or model usage payload. |
| Evidence-first gateway | Harness validation and operator evidence chains | Runtime claims are backed by logs, jobs, idempotency, outbox, smoke, failure diagnosis, and bundle digests. | Scenario matrix, smoke verifier, `yinyo.trace_failure_diagnosis.v1`, diagnostics, bundle verifier, and release audit. | Verified ws redacted bundle with runtime/job/event/smoke chain and advanced records. |
| State handoff | Harness state-transfer and trace continuity practice | A future operator or agent can resume from a structured packet instead of reconstructing intent from chat. | `state_handoff` scenario with handoff schema, correlation id, permissions, source audit, artifacts, manifest link, budget state, trace history, and `yinyo.handoff_resume.v1` replay proof. | Included in the verified ws redacted bundle or release handoff packet. |

The local release matrix proves harness mechanisms against the versioned harness corpus in `corpus/harness/scenarios.v1.json`. The corpus now owns the contracts for image understanding, long-context retention, memory supersession, memory durability, TemporalTree state recovery, Trace2Skill promotion, ACK boundary, worker saturation, runtime single-writer locking, workspace boundary enforcement, trace-native failure diagnosis, DeepSeek usage, adaptive simplification, partial failure, and release blocking. It does not prove the public `1.0.0` product until the matching live Feishu evidence exists.
The same matrix also emits `harness_layers.schema = yinyo.harness_layers.v1`, an ETCLOVG layer coverage table that fails if Execution, Tooling, Context, Lifecycle, Observability, Verification, or Governance lacks executable proof, and a `yinyo.proof_ablation.v1` adaptive-simplification report that proves load-bearing proofs cannot be removed silently.

---

## Harness Engineering Alignment

The 2026 Agent Harness Engineering survey frames the harness as an independent
system layer and separates it into ETCLOVG: Execution, Tooling, Context,
Lifecycle, Observability, Verification, and Governance. YINYO uses that taxonomy
as an architecture coverage checklist, not as a marketing label.

Reference: https://picrew.github.io/LLM-Harness/

| ETCLOVG layer | YINYO local surface | Acceptance implication |
|---------------|---------------------|------------------------|
| Execution | `yinyo serve`, runtime store lock, bounded job workers, ACK boundary, workspace isolation, tool resource quotas | Local service startup, worker saturation, ACK-before-agent execution, workspace-boundary, and resource-quota corpus proof must show where code runs, when work is rejected, and which local tool calls are bounded. |
| Tooling | small built-in tool surface, Feishu adapter, outbox boundary, image adapter | Tool calls and Feishu sends must pass through typed wrappers with evidence, fallback, and explicit failure states. |
| Context | ContextManager, TemporalTree, memory durability policy, source-required answers | Long sessions must preserve protected recent context, reject ephemeral memory, recover state from disk, report provenance/staleness, and mark current-fact answers without sources. |
| Lifecycle | Runtime gateway, idempotency store, job queue, Trace2Skill, smoke workflow | Events must move through ACK, durable job state, agent run, delivery, diagnostics, and replayable promotion records. |
| Observability | runtime JSONL, job JSONL, smoke JSONL, manifests, model usage, diagnostics | Claims require correlated traces, costs, failures, root-cause diagnosis, and operator-readable diagnostics, not only final replies. |
| Verification | local release matrix, scenario replay, bundle verifier, strict release gate, proof ablation | Scenario results must become trace-native proof envelopes, diagnosis records must cite trace refs, matrix rows must reject weak `passed=True` fixtures, and ablation reports must show which rows or layers fail when a load-bearing proof is removed. |
| Governance | governance policy, confirmation metadata, secret scan, redacted bundles, release boundary | Risk, secrets, live evidence, and unsupported release states must be enforced by tests and verifiers. |

This adds three development rules:

- Treat traces as the primary proof object for outcome, failure attribution, and
  regression, not as after-the-fact logs.
- Treat handoff as state transfer: intent, constraints, permissions, artifacts,
  provenance, budget, risk, trace history, and unresolved decisions belong in
  handoff records when they affect future work.
- Simplify harness layers only after ablation or release-matrix evidence proves
  the layer is no longer load-bearing for quality, latency, cost, or risk.

---

## Release Gates

### P0: Real Local Loop

P0 is the minimum usable agent. These checks must pass before higher-level memory,
evolution, or Feishu claims are expanded.

| ID | Capability | Acceptance |
|----|------------|------------|
| P0-01 | Workspace isolation | `YinyoAgent(workspace=ws)` makes built-in file tools resolve relative paths inside `ws`, and blocks absolute or traversal paths. |
| P0-02 | Tool confirmation | Tools marked `CONFIRM` do not run through the agent loop unless the call carries structured confirmation metadata with `actor`, tool-scoped `scope`, `reason`, and future `expires_at`; legacy `_confirmed` booleans are rejected. |
| P0-03 | Evidence | Every executed or blocked tool call writes an evidence record with redacted arguments/results. |
| P0-04 | Status truth | A run with blocked verification returns a non-success status or explicit partial status; it must not look fully successful. |
| P0-05 | UTF-8 persistence | `manifest.json`, evidence, changes, and memory files are written with UTF-8 on Windows and Linux. |
| P0-06 | Delegate wiring | `delegate_task` can reach the active parent agent and returns a worker trace instead of `no parent agent found`. |
| P0-07 | Package import | `import yinyo; yinyo.YinyoAgent(...)` works without relying on the caller's current directory. |
| P0-08 | Resource quotas | Built-in read, search, and shell tools expose bounded local resource behavior: read limits are honored, search results are capped, oversized files are skipped during content search, shell output is truncated, and command timeouts return blocked evidence instead of unbounded execution. |

### P1: Product Loop

| ID | Capability | Acceptance |
|----|------------|------------|
| P1-01 | Feishu webhook | URL verification checks the configured token; event callbacks with a bad token are rejected; text events route through `handle_message`; image events call the vision adapter path. These paths are covered by unit tests without requiring a live Feishu app. |
| P1-02 | Memory evolution | A newer contradictory fact supersedes the old fact either through explicit `supersedes` metadata or same-scope conflict detection. Search excludes superseded facts and `get_audit_trail()` returns both versions. |
| P1-03 | Reflection | Auto-reflect can update memory only through structured, validated operations. Empty values, oversized facts, wrong types, ambiguous replacements, and malformed JSON do not mutate memory. |
| P1-04 | DeepSeek fallback | Provider fallback is observable in the run result metadata and in `changes.jsonl`, and is tested with mocked provider failures. |
| P1-05 | Manifest | Any successful file-changing run (`do_write`, `do_edit`, `do_patch`) generates `manifests/{run_id}.json` from actual tool traces, including affected files and evidence refs. Pure conversation runs and blocked writes do not create file-change manifests. |
| P1-06 | State handoff | Every run writes `runs/{run_id}/handoff.json` with schema, intent, constraints, permissions, artifacts, provenance, budget state, trace history, risk notes, unresolved items, and the run manifest links to it. `replay_handoff()` returns `yinyo.handoff_resume.v1` with inherited state, resolved artifact paths, artifact existence diagnostics, and `resume_ready=true` only when required packet fields are reusable. |

### P2: Evolution

P2 capabilities are not product claims until P0 and P1 are green.

| ID | Capability | Acceptance |
|----|------------|------------|
| P2-01 | Trace2Skill | Repeated failures create a draft skill and a regression fixture under `skills/{name}/regression.json`. The fixture records task, error, pattern keywords, expected guardrails, and a replay command, so the failure can be executed before promoting the skill. |
| P2-02 | Blind test | A validation runner executes a test command in a separate subprocess and records `command`, `exit_code`, `stdout_tail`, `stderr_tail`, `passed`, and timestamp under `validation/{run_id}.json`. Manifest verification can consume this record instead of handwritten pass/fail claims. |
| P2-03 | Long context | Context management exposes a retention report for synthetic long sessions: estimated tokens, number of masked observations, compression count, DAG nodes written, and whether protected recent messages remain present after auto-manage. |

### P3: Feishu Runtime Gateway

P3 turns the Feishu path from an adapter callback into a deployable runtime
boundary. It stays Feishu-only; it is not a generic multi-platform gateway.

| ID | Capability | Acceptance |
|----|------------|------------|
| P3-01 | Fast ACK boundary | Webhook handling verifies Feishu tokens, normalizes supported events, enqueues a runtime job, and returns HTTP-style ACK without running the agent inline when async dispatch is enabled. |
| P3-02 | Idempotency | Duplicate Feishu events identified by `uuid`, `event_id`, or `message_id` do not enqueue or execute a second job. |
| P3-03 | Runtime job tracking | Each accepted message creates a job record with id, kind, payload, status, timestamps, result, and error. Synchronous test mode can force the job to completion without threads. |
| P3-04 | Outbox boundary | Processing reactions and reply delivery go through an outbox wrapper so gateway execution is separated from Feishu API send side effects. |
| P3-05 | Adapter compatibility | `FeishuAdapter.handle_webhook_event(..., async_dispatch=False)` keeps the P1 unit-test contract while delegating runtime orchestration to the gateway. |

### P4: Deployable Feishu Service

P4 makes the alpha runnable as a service with explicit configuration and
operator evidence.

| ID | Capability | Acceptance |
|----|------------|------------|
| P4-01 | Service entry | `yinyo serve` builds a `YinyoAgent`, `FeishuAdapter`, and runtime gateway from typed config, then starts the webhook server with explicit host, port, and workspace. |
| P4-02 | Config validation | Missing required Feishu/DeepSeek settings fail fast with actionable errors and without echoing secret values. |
| P4-03 | Durable idempotency | Duplicate event protection survives process restart through a local event store. |
| P4-04 | Structured logs | Webhook acceptance, duplicate suppression, job completion, and outbox delivery emit JSONL records with a shared correlation id. |
| P4-05 | Smoke evidence | Live-smoke evidence is written as redacted JSONL records for transport-scoped basic scenarios, message replies, and failure scenarios. Advanced records include controlled-recorder proof digests and `yinyo.advanced_ref_resolution.v1` status so path-like run, skill, validation, usage, memory, and failure references are resolved or explicitly rejected. Bundles preserve that build-time ref/proof summary as `yinyo.advanced_ref_attestation.v1` so redacted transfer verification can reject drift without reopening raw local refs. |

---

## Development Rule

Do not add a new architecture claim without adding an acceptance check here. If a
claim cannot be tested yet, label it as target state in documentation and keep it
out of the product capability list.

---

## 1.0 Release Criteria

`1.0.0` is an external product release, not an internal engineering milestone.
Before YINYO can be called `1.0.0`, all of the following must be true:

| ID | Requirement | Evidence |
|----|-------------|----------|
| R1-01 | All internal acceptance gates required for the release are green in CI and local development. | Test command, CI run, and passing result. |
| R1-02 | A fresh install works in a clean virtual environment. | Install command and import/CLI smoke output. |
| R1-03 | Core Feishu workflows pass against a live Feishu app. | Redacted ws runtime, text, image, card, and duplicate-event evidence; HTTP URL verification is required only when validating the HTTP fallback path. |
| R1-04 | Security boundaries are current. | `SECURITY.md`, secret scan result, and blocked-risk tests. |
| R1-05 | Public docs match implemented behavior. | README claims trace back to tests, source, or explicit target-state labels. |
| R1-06 | Release metadata uses external SemVer only. | `pyproject.toml`, `yinyo.__version__`, tag, and changelog agree. |
| R1-07 | Feishu long-connection is the primary transport and HTTP webhook remains a tested fallback. | Live long-connection startup log, local SDK-contract tests, and HTTP fallback scenario replay. |
| R1-08 | Advanced product workflows are not deferred. | End-to-end fixtures and live Feishu evidence for long conversation, image understanding, card fallback, memory supersession, and partial failure language. |
| R1-09 | Trace2Skill is a complete lifecycle, not a draft artifact. | Failure trace, generated skill, regression replay before promotion, promotion record, post-promotion pass evidence, and live Feishu skill evidence. |
| R1-10 | DeepSeek adaptation is measured. | Per-run token/cost telemetry, timeout/retry/fallback attempts, documented degradation behavior, and live Feishu usage evidence. |
| R1-11 | 3+6 product traits are each backed by evidence. | A release evidence matrix mapping every product core, behavioral trait, and ETCLOVG harness layer to tests, fixtures, live smoke records, live advanced workflow records, resolved evidence references, or explicit unsupported boundaries. |
