<div align="center">

# YINYO

"A harness Agent for Feishu + DeepSeek workflows that remembers, verifies, and improves."

![Status](https://img.shields.io/badge/status-lite-2ea043)
![Version](https://img.shields.io/badge/version-1.0.0--lite-2ea043)
![Scope](https://img.shields.io/badge/scope-harness--agent-blue)
![Tests](https://img.shields.io/badge/tests-356%20local-2ea043)
![Release](https://img.shields.io/badge/1.0-blocked%20by%20live%20smoke-d73a49)

</div>

YINYO is a focused harness Agent product benchmarked against Hermes and OpenClaw design expectations. It uses Feishu and DeepSeek as the first product surface, then combines a runtime gateway, DeepSeek-first model gateway, TemporalTree memory, Trace2Skill evolution, evidence records, and release gates into one deployable product line. See [docs/benchmarking.md](docs/benchmarking.md) for the comparison method and limits.

[Quick Start](#quick-start) · [External Testing](#external-testing) · [Product Constitution](#product-constitution) · [What It Does](#what-it-does) · [Runtime](#runtime) · [Release Status](#release-status) · [Boundaries](#boundaries) · [Validation](#validation)

---

## Quick Start

```bash
pip install yinyo-agent
cp yinyo.env.example yinyo.env
yinyo serve --workspace ./workspace --profile local --transport ws
```

For a local config check without starting the service:

```bash
yinyo serve --workspace ./workspace --dry-run
```

---

## External Testing

GitHub users can test `v1.0.0-lite` against a real Feishu app. Follow
[docs/external-testing.md](docs/external-testing.md) to clone or install YINYO,
configure a self-built Feishu app, run the long-connection service, collect
redacted smoke evidence, and share a `smoke-bundle` without secrets.
Use [RELEASE_NOTES.md](RELEASE_NOTES.md) as the GitHub Release body and asset
checklist for `v1.0.0-lite`.

External live reports are welcome, but they do not make `v1.0.0` publishable
until the strict candidate guard passes with a verified ws bundle:

```bash
python scripts/verify_release.py --target 1.0.0 --bundle <bundle-dir> --candidate 1.0.0
```

---

## Product Constitution

YINYO keeps three product cores:

| Core | Meaning |
|---|---|
| Less is more | Feishu first, small audited tool surface, no platform sprawl. |
| Borrow what works | Research-inspired memory, context, and evolution mechanisms must produce testable behavior. |
| DeepSeek adapted | Large context, low-cost calls, tool calling, retry/fallback, and usage telemetry are first-class design assumptions. |

It also keeps six behavioral traits: curiosity, reliability, fact hygiene, multidisciplinary thinking, negative capability, and low ego with high drive. The release matrix maps every core and trait to executable local evidence, then `1.0.0` requires live Feishu evidence for the same product claims. The public matrix is indexed in [docs/release-evidence-matrix.md](docs/release-evidence-matrix.md).

---

## What It Does

| Capability | Product path |
|---|---|
| Harness runtime | Feishu long-connection transport, HTTP fallback, event verification, idempotency, jobs, outbox, and smoke evidence. |
| DeepSeek-first execution | Provider chain, usage accounting, retry/fallback metadata, and cost estimates in run manifests. |
| Durable memory | TemporalTree facts evolve through supersession instead of piling up stale notes. |
| Self-improvement | Trace2Skill extracts repeated failure patterns into skills, records regression fixtures, and promotes only after replay evidence. |
| Evidence hygiene | Tool calls, blocked actions, redacted smoke records, and release checks are persisted. |
| 3+6 evidence matrix | Scenario replay maps product cores and behavioral traits to executable checks. |

---

## Runtime

The default product transport is Feishu long connection (`ws`). HTTP webhook remains as a fallback and local diagnostic path.

---

## Release Status

Current external version: `1.0.0-lite`

Python package version: `1.0.0rc1`

This is the public lite line for GitHub download and real Feishu validation, not the full stable `1.0.0` release. The historical `v8.x` labels are internal prototype milestones and are no longer public product versions.

`1.0.0` is blocked until live Feishu smoke evidence proves:

| Smoke scenario | Required |
|---|---:|
| URL verification | HTTP only |
| Text message reply | yes |
| Image message reply | yes |
| Card fallback | yes |
| Duplicate callback | yes |

It also requires live advanced Feishu records for image understanding, long conversation, memory supersession, Trace2Skill promotion, DeepSeek usage telemetry, and partial failure behavior. Local replay alone is not enough for `1.0.0`.

---

## Boundaries

YINYO intentionally focuses on Feishu and DeepSeek-centered agent workflows. It does not aim to be a universal multi-platform agent gateway.

The current release matrix now runs executable local evidence for image understanding, long-context retention, memory supersession, TemporalTree state recovery, Trace2Skill promotion, ACK boundary, worker saturation, runtime single-writer locking, workspace boundary enforcement, resource quotas, trace-native failure diagnosis, state handoff, model usage, adaptive simplification, card fallback, partial failure, and release blocking. Those high-value local scenarios are bound to a versioned harness corpus. Real Feishu live smoke is still required before `1.0.0`.

The `1.0.0` gate requires smoke records to be backed by matching runtime logs, durable job records, event idempotency records, and the single-writer runtime lock used by local JSONL stores.

---

## Validation

```bash
python scripts/replay_scenarios.py --matrix
python -m yinyo.cli config template --live-smoke > yinyo.env
python -m yinyo.cli smoke runbook --config ./yinyo.env
python -m yinyo.cli smoke preflight --config ./yinyo.env
python -m yinyo.cli smoke status --config ./yinyo.env
python scripts/verify_secrets.py
python scripts/verify_release.py
python scripts/verify_release.py --json
python scripts/verify_public_tree.py
python -m pytest tests -q
python -m build
python scripts/verify_wheel.py --skip-build
```

For a `1.0.0` release candidate:

```bash
python -m yinyo.cli config template --live-smoke > yinyo.env
python -m yinyo.cli smoke runbook --config ./yinyo.env
python -m yinyo.cli smoke preflight --config ./yinyo.env
python -m yinyo.cli smoke reset --config ./yinyo.env --confirm-reset
python -m yinyo.cli serve --config ./yinyo.env
# Keep the service running, complete text/image/card-fallback/duplicate Feishu live actions, then record advanced evidence.
python -m yinyo.cli smoke record-advanced --config ./yinyo.env --scenario image_understanding --image-ref <redacted-image-ref>
python -m yinyo.cli smoke record-advanced --config ./yinyo.env --scenario long_conversation --transcript-ref <redacted-transcript-ref>
python -m yinyo.cli smoke record-advanced --config ./yinyo.env --scenario memory_supersession --memory-ref <redacted-memory-ref>
python -m yinyo.cli smoke record-advanced --config ./yinyo.env --scenario trace2skill_promotion --failure-trace-ref <redacted-failure-trace-ref> --skill-ref <redacted-skill-ref> --regression-result-ref <redacted-regression-result-ref> --promotion-status proven --post-promotion-run-ref <redacted-run-ref>
python -m yinyo.cli smoke record-advanced --config ./yinyo.env --scenario deepseek_usage --usage-ref <redacted-usage-ref>
python -m yinyo.cli smoke record-advanced --config ./yinyo.env --scenario partial_failure --failure-ref <redacted-failure-ref>
python -m yinyo.cli smoke wait --config ./yinyo.env
python -m yinyo.cli smoke status --config ./yinyo.env
python -m yinyo.cli smoke bundle --config ./yinyo.env --output ./workspace/smoke-bundle --handoff-dir ./workspace/runs --live-attestation-id <attestation-id> --tenant-hash <sha256-tenant>
python scripts/verify_release.py --bundle ./workspace/smoke-bundle
python scripts/verify_release.py --target 1.0.0 --bundle ./workspace/smoke-bundle
python scripts/verify_release.py --target 1.0.0 --bundle ./workspace/smoke-bundle --candidate 1.0.0
python scripts/prepare_release_metadata.py --version 1.0.0 --verified-bundle ./workspace/smoke-bundle
python scripts/prepare_release_metadata.py --version 1.0.0 --verified-bundle ./workspace/smoke-bundle --apply
python scripts/verify_release.py --target 1.0.0 --bundle ./workspace/smoke-bundle --candidate 1.0.0
python scripts/verify_release.py --target 1.0.0 --config ./yinyo.env
python scripts/verify_release.py --target 1.0.0 --config ./yinyo.env --json
```

The runbook embeds the current evidence snapshot, `operator_plan`, and `yinyo.frontier_readiness.v1`, so the live operator can see missing basic, advanced, runtime, diagnostic, handoff, and frontier-harness layers before collecting evidence.

The release verifier emits a machine-readable R1 readiness audit in JSON mode, covering every `docs/spec.md` 1.0 release criterion. Advanced live records must be captured through `yinyo smoke record-advanced`; handwritten advanced JSONL records are rejected by the 1.0 evidence verifier. The recorder adds a `yinyo.advanced_live_proof.v1` digest over the redacted required fields, and the verifier rejects missing or mismatched advanced proofs.

Release metadata promotion is deliberately gated: `prepare_release_metadata.py --apply` for `1.0.0` requires `--verified-bundle <dir>` and refuses unverified or non-ws bundles.

Candidate `1.0.0` requires a `transport=ws` long-connection bundle; HTTP evidence remains a fallback check, not the primary release proof. The ws bundle must also contain at least one run-level `handoff.json` that replays through `replay_handoff()` into `yinyo.handoff_resume.v1`, so `handoff_ready_records > 0`, plus redacted `service_start` with `smoke_mode=false`, `ws_transport_start`, and same-`event_key` `ws_event_received` runtime logs for every basic smoke scenario, with startup config fields and ACK metrics inside the Feishu deadline. HTTP `url_verification` evidence is not required for the primary ws release path. Bundle manifests include SHA-256 hashes for each redacted evidence and handoff file plus a stable `bundle_digest`; verification rejects replaced files, malformed or unreplayable handoff packets, digest mismatches, `yinyo.advanced_ref_attestation.v1` drift, or frontier readiness gaps across ETCLOVG, TemporalTree, trace diagnosis, handoff, and adaptive simplification proof. Candidate bundles also require manifest `yinyo.live_provenance.v1` with a redacted operator attestation id, Feishu app hash, tenant hash, and ws SDK session id; the verifier cross-checks `live_provenance.ws_sdk_session_id` against the redacted runtime log `service_start` and `ws_transport_start` `ws_sdk_session_id` markers so local synthetic fixtures cannot stand in for live Feishu evidence.

`yinyo smoke bundle` inherits `ws_sdk_session_id` from `yinyo.env`; if `--ws-sdk-session-id` is provided, it must match the config value.
It also computes `feishu_app_id_hash` as `sha256(app_id)` from config; if `--feishu-app-id-hash` is provided, it must match `sha256(app_id)`.

For the live `card_fallback` smoke scenario, temporarily set `smoke_mode=true` in `yinyo.env` and send `/yinyo-smoke card-fallback`. Then turn smoke mode off, restart, collect the remaining live scenarios, and build the final bundle.

---

## Documents

| Document | Purpose |
|---|---|
| [docs/external-testing.md](docs/external-testing.md) | GitHub tester guide for real Feishu validation and redacted bundle sharing. |
| [docs/release-evidence-matrix.md](docs/release-evidence-matrix.md) | Public 3+6 and ETCLOVG evidence index. |
| [docs/benchmarking.md](docs/benchmarking.md) | Hermes/OpenClaw comparison method and limits. |
| [docs/spec.md](docs/spec.md) | Product spec and acceptance gates. |
| [docs/handoff.md](docs/handoff.md) | Cross-session product context and current evidence boundary. |
| [docs/roadmap.md](docs/roadmap.md) | Gap from alpha to `1.0.0`. |
| [docs/deployment.md](docs/deployment.md) | Service deployment and smoke workflow. |
| [docs/production-checklist.md](docs/production-checklist.md) | Release preparation checklist. |
| [docs/versioning.md](docs/versioning.md) | External SemVer and internal gate policy. |
| [RELEASE_NOTES.md](RELEASE_NOTES.md) | GitHub Release body and asset checklist for `v1.0.0-lite`. |
| [MAINTENANCE.md](MAINTENANCE.md) | Maintenance and validation commands. |
| [SECURITY.md](SECURITY.md) | Security and data-boundary policy. |
| [AGENTS.md](AGENTS.md) | Collaboration rules for future agents. |

---

## License

MIT (c) 2026 Yinyo Contributors
