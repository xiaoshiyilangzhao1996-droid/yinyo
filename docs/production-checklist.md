# Production Checklist

YINYO `1.0.0-lite` is publishable for GitHub download and real Feishu
validation. This checklist defines what must be true before a full stable
`1.0.0` release.

---

## Runtime

- [ ] `yinyo serve --config ./yinyo.env --dry-run` passes with redacted output.
- [ ] `yinyo.env.example`, `yinyo config template`, or `yinyo config template --live-smoke` was used to create the local config skeleton.
- [ ] `yinyo smoke runbook --config ./yinyo.env` prints the live smoke, diagnostics, 3+6 replay, `1.0.0` release-gate sequence, current evidence snapshot, missing chain layers, `operator_plan`, and `yinyo.frontier_readiness.v1`.
- [ ] `yinyo smoke preflight --config ./yinyo.env` passes before live smoke, reports no existing smoke/runtime/job/event-store evidence files, and validates `ws_sdk_session_id` live provenance readiness.
- [ ] `yinyo smoke reset --config ./yinyo.env --confirm-reset` is run before a fresh live smoke attempt.
- [ ] `yinyo smoke wait --config ./yinyo.env` reaches OK only after basic runtime evidence and advanced live evidence are both complete; if it exits nonzero, run `yinyo smoke status --config ./yinyo.env --json` and follow `operator_plan`.
- [ ] `yinyo smoke status --config ./yinyo.env` reports OK, or its next actions are resolved before release review.
- [ ] Service starts with explicit `profile`, `transport`, and `workspace`.
- [ ] `smoke_mode=true` is used only during live release smoke and disabled afterward.
- [ ] `profile=production` configs do not set `smoke_mode=true`; validation rejects this state.
- [ ] Long-connection mode is enabled in the Feishu self-built app, or HTTP mode has a reachable callback URL.
- [ ] Long-connection `ack_latency_ms` stays below `ack_deadline_ms` in
  `runtime.jsonl`.
- [ ] The redacted ws smoke bundle contains `service_start`,
  `ws_transport_start`, and same-`event_key` `ws_event_received` runtime logs
  for every basic smoke scenario, with startup config fields and ACK metrics.
- [ ] `runtime.jsonl`, `runtime_jobs.jsonl`, `gateway_events.jsonl`, and
  `smoke_evidence.jsonl` are stored on durable local storage.
- [ ] `yinyo diagnose --config ./yinyo.env --json` reports nonzero event-store keys after live message callbacks.
- [ ] `yinyo diagnose --config ./yinyo.env --json` reports service lifecycle status and no failed `service_stop`.
- [ ] Local JSONL stores have a single process writer, or an external shared store is used.
- [ ] `runtime_lock_path` lives on durable local storage and blocks a second local service process.
- [ ] Any stale same-host runtime lock was recovered by preflight/startup; foreign-host or unknown lock owners were inspected instead of deleted blindly.
- [ ] Each `smoke_evidence.jsonl` scenario has matching runtime log, durable job, and event-store evidence where applicable.
- [ ] `yinyo diagnose --config ./yinyo.env` returns OK after live smoke.
- [ ] Only one worker writes to a local event/job store, or an external shared
  store adapter is used.

---

## Feishu

- [ ] Long-connection event subscriptions are enabled for the real Feishu app.
- [ ] URL verification passes against the real Feishu app only when testing the HTTP fallback path.
- [ ] Text message receive/reply passes.
- [ ] Image message receive/reply or graceful vision failure passes.
- [ ] Card fallback to text is verified with `/yinyo-smoke card-fallback` while smoke mode is enabled.
- [ ] Duplicate callback suppression is verified.
- [ ] Redacted smoke evidence is saved.
- [ ] Live advanced evidence is saved for image understanding, long conversation, memory supersession, Trace2Skill promotion, DeepSeek usage, and partial failure.
- [ ] Advanced evidence is recorded through `yinyo smoke record-advanced`, not by hand-editing JSONL; verifier output has no `advanced_source_missing` entries.
- [ ] Advanced records include `yinyo.advanced_live_proof.v1`; verifier output has no `advanced_proof_missing` or `advanced_proof_mismatch` entries.
- [ ] Path-like advanced refs resolve cleanly; verifier output has no `advanced_ref_unresolved` entries.
- [ ] `yinyo smoke bundle --config ./yinyo.env --output <bundle-dir> --handoff-dir ./workspace/runs --live-attestation-id <attestation-id> --tenant-hash <sha256-tenant>` succeeds and the bundle is used for release review.
- [ ] The bundle manifest `file_hashes` cover every redacted evidence and handoff file, `bundle_digest` is present, and `python scripts/verify_release.py --bundle <bundle-dir>` passes after transfer.
- [ ] The bundle manifest `advanced_ref_attestation.schema` is `yinyo.advanced_ref_attestation.v1`, its digest verifies, and no scenario was attested from `skipped_for_redacted_bundle` refs.
- [ ] The bundle manifest `frontier_readiness.schema` is `yinyo.frontier_readiness.v1` and its checks cover ETCLOVG local layer coverage, TemporalTree state continuity, trace-native failure diagnosis, state handoff transfer, and adaptive simplification guard.
- [ ] The ws bundle manifest has `handoffs.ready_records > 0` and `frontier_readiness.handoff_ready_records > 0`; each ready handoff must replay through `replay_handoff()` into `yinyo.handoff_resume.v1`.
- [ ] The bundle manifest `live_provenance.schema` is `yinyo.live_provenance.v1` and contains non-placeholder operator attestation, Feishu app hash, tenant hash, and ws SDK session id values.
- [ ] `yinyo smoke bundle` inherits `ws_sdk_session_id` from `yinyo.env` or receives a matching `--ws-sdk-session-id`; `--ws-sdk-session-id` must match `ws_sdk_session_id` when both are present.
- [ ] `yinyo smoke bundle` computes `feishu_app_id_hash` as `sha256(app_id)` from config; `--feishu-app-id-hash` must match `sha256(app_id)` when provided.
- [ ] `live_provenance.ws_sdk_session_id` matches the latest `service_start` and `ws_transport_start` `ws_sdk_session_id` markers in the redacted runtime log.
- [ ] The final `1.0.0` bundle manifest records `transport=ws`, a latest `service_start` with `smoke_mode=false`, and at least one replayable run-level `handoff.json`; HTTP evidence is retained only as fallback coverage.
- [ ] Handwritten smoke records alone do not pass the release gate.

---

## Security

- [ ] Feishu app secret, verify token, tenant token, and model keys are not in git.
- [ ] Logs and smoke evidence are redacted before sharing.
- [ ] `python scripts/verify_secrets.py` passes.
- [ ] Incident playbook has been reviewed.
- [ ] Dedicated keys are used for this deployment.
- [ ] The process runs inside an OS/container boundary appropriate for the risk.

---

## Release

- [ ] `python scripts/verify_release.py`
- [ ] `python scripts/verify_release.py --json` has an R1 item for every `docs/spec.md` 1.0 criterion.
- [ ] `python scripts/verify_secrets.py`
- [ ] `python -m yinyo.cli smoke runbook --config ./yinyo.env`
- [ ] `python -m yinyo.cli smoke preflight --config ./yinyo.env`
- [ ] `python -m yinyo.cli smoke reset --config ./yinyo.env --confirm-reset`
- [ ] `python -m yinyo.cli serve --config ./yinyo.env` is running while the operator completes text, image, card-fallback, and duplicate Feishu live actions.
- [ ] `python -m yinyo.cli smoke record-advanced --config ./yinyo.env --scenario image_understanding --image-ref <ref> --run-id <run>`
- [ ] `python -m yinyo.cli smoke record-advanced --config ./yinyo.env --scenario long_conversation --transcript-ref <ref> --run-id <run>`
- [ ] `python -m yinyo.cli smoke record-advanced --config ./yinyo.env --scenario memory_supersession --memory-ref <ref> --run-id <run>`
- [ ] `python -m yinyo.cli smoke record-advanced --config ./yinyo.env --scenario trace2skill_promotion --failure-trace-ref <ref> --skill-ref <ref> --regression-result-ref <ref> --promotion-status proven --post-promotion-run-ref <ref>`
- [ ] `python -m yinyo.cli smoke record-advanced --config ./yinyo.env --scenario deepseek_usage --usage-ref <ref> --model-usage '{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}'`
- [ ] `python -m yinyo.cli smoke record-advanced --config ./yinyo.env --scenario partial_failure --failure-ref <ref> --run-id <run>`
- [ ] `python -m yinyo.cli smoke wait --config ./yinyo.env --timeout <seconds>`
- [ ] `python -m yinyo.cli smoke status --config ./yinyo.env`
- [ ] `python -m yinyo.cli smoke verify --transport ws --path ./workspace/smoke_evidence.jsonl`
- [ ] `python -m yinyo.cli smoke verify --transport ws --path ./workspace/smoke_evidence.jsonl --json`
- [ ] `python -m yinyo.cli smoke bundle --config ./yinyo.env --output <bundle-dir> --handoff-dir ./workspace/runs --live-attestation-id <attestation-id> --tenant-hash <sha256-tenant>`
- [ ] `python scripts/verify_release.py --bundle <bundle-dir>`
- [ ] `python scripts/verify_release.py --target 1.0.0 --bundle <bundle-dir>`
- [ ] `python scripts/verify_release.py --target 1.0.0 --bundle <bundle-dir> --candidate 1.0.0`
- [ ] `python scripts/prepare_release_metadata.py --version 1.0.0 --verified-bundle <bundle-dir>`
- [ ] `python scripts/prepare_release_metadata.py --version 1.0.0 --verified-bundle <bundle-dir> --apply`
- [ ] `python scripts/verify_release.py --target 1.0.0 --bundle <bundle-dir> --candidate 1.0.0` passes after metadata promotion.
- [ ] `python scripts/replay_scenarios.py`
- [ ] `python scripts/replay_scenarios.py --matrix`
- [ ] `python -m pytest tests -q`
- [ ] `python -m build`
- [ ] `python scripts/verify_wheel.py --skip-build`
- [ ] `python scripts/verify_release.py --target 1.0.0 --config ./yinyo.env` passes.
- [ ] `python scripts/verify_release.py --target 1.0.0 --config ./yinyo.env --json` passes with all R1 items green.
- [ ] `.github/workflows/release.yml` passes for the target version with `runtime_config_path`, `smoke_bundle_path`, and `candidate=1.0.0` set for `1.0.0`.
- [ ] The CI runner can access the redacted smoke bundle path used for `smoke_bundle_path`; do not dispatch a private local absolute path that CI cannot read.

`1.0.0` must not be tagged while any item above is unchecked.

---

## 3+6 Evidence

- [ ] Less is more: Feishu-only boundaries and unsupported platforms are explicit.
- [ ] Borrow what works: memory, long context, Trace2Skill regression replay validation, and card fallback each have product-level fixtures.
- [ ] Execution hardening: `yinyo.resource_quota.v1` proves read/search/output/timeout limits before any tool permission expansion.
- [ ] DeepSeek adapted: token/cost telemetry, fallback attempts, `model_error` exhaustions, and degradation behavior are recorded.
- [ ] Curiosity: reflection writes only durable user/project facts.
- [ ] Reliability: ws live smoke, scenario replay, diagnostics, and release gates all pass.
- [ ] Fact hygiene: external/current fact answers without citations return `source_required`, the user-visible reply asks for cited verification, and shared evidence is redacted.
- [ ] Multidisciplinary thinking: research-inspired mechanisms prove workflow value through fixtures.
- [ ] Negative capability: partial failures are visible to the user and operator.
- [ ] Low ego, high drive: no README claim depends on self-reported pass rates without artifacts.
- [ ] R1-05: README claims trace back to tests, source, or explicit target-state labels.
