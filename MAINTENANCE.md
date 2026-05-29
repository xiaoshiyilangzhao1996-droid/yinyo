<div align="center">

# YINYO Maintenance

"Keep release claims tied to evidence."

![Status](https://img.shields.io/badge/status-lite-2ea043)
![Release](https://img.shields.io/badge/release-1.0.0rc1-2ea043)
![Scope](https://img.shields.io/badge/scope-feishu--only-blue)

</div>

Operational maintenance and release checks for YINYO.

## Project Home

Run commands from the checked-out repository root:

```text
<repo>
```

Do not treat dated session directories, exported chat logs, build outputs, or
live smoke workspaces as the primary project root. Keep repo-level docs, tests,
local release checks, and smoke-bundle work anchored to a stable standalone
checkout.

[Daily Checks](#daily-checks) · [Release Gate](#release-gate) · [Smoke Evidence](#smoke-evidence) · [Incidents](#incidents) · [Versioning](#versioning)

---

## Daily Checks

```bash
python -m pytest tests -q
python -m yinyo.cli serve --dry-run
```

The second command should fail without secrets and must not print secret values.
Use a real config file only on a trusted local machine.

---

## Release Gate

Before tagging any release:

```bash
python scripts/verify_release.py
python scripts/verify_release.py --json
python scripts/verify_public_tree.py
python scripts/verify_secrets.py
python -m yinyo.cli config template --live-smoke > yinyo.env
python -m yinyo.cli smoke runbook --config ./yinyo.env
python -m yinyo.cli smoke preflight --config ./yinyo.env
python -m yinyo.cli smoke reset --config ./yinyo.env --confirm-reset
python -m yinyo.cli serve --config ./yinyo.env
# Keep serve running while completing text/image/card-fallback/duplicate Feishu live actions.
python -m yinyo.cli smoke record-advanced --config ./yinyo.env --scenario image_understanding --image-ref <ref> --run-id <run>
python -m yinyo.cli smoke record-advanced --config ./yinyo.env --scenario long_conversation --transcript-ref <ref> --run-id <run>
python -m yinyo.cli smoke record-advanced --config ./yinyo.env --scenario memory_supersession --memory-ref <ref> --run-id <run>
python -m yinyo.cli smoke record-advanced --config ./yinyo.env --scenario trace2skill_promotion --failure-trace-ref <ref> --skill-ref <ref> --regression-result-ref <ref> --promotion-status proven --post-promotion-run-ref <ref>
python -m yinyo.cli smoke record-advanced --config ./yinyo.env --scenario deepseek_usage --usage-ref <ref> --model-usage '{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}'
python -m yinyo.cli smoke record-advanced --config ./yinyo.env --scenario partial_failure --failure-ref <ref> --run-id <run>
python -m yinyo.cli smoke wait --config ./yinyo.env
python -m yinyo.cli smoke status --config ./yinyo.env
python -m yinyo.cli smoke bundle --config ./yinyo.env --output ./workspace/smoke-bundle --handoff-dir ./workspace/runs --live-attestation-id <attestation-id> --tenant-hash <sha256-tenant>
python scripts/verify_release.py --bundle ./workspace/smoke-bundle
python scripts/verify_release.py --target 1.0.0 --bundle ./workspace/smoke-bundle
python scripts/verify_release.py --target 1.0.0 --bundle ./workspace/smoke-bundle --candidate 1.0.0
python scripts/prepare_release_metadata.py --version 1.0.0 --verified-bundle ./workspace/smoke-bundle
python scripts/prepare_release_metadata.py --version 1.0.0 --verified-bundle ./workspace/smoke-bundle --apply
python scripts/verify_release.py --target 1.0.0 --bundle ./workspace/smoke-bundle --candidate 1.0.0
python scripts/replay_scenarios.py
python scripts/replay_scenarios.py --matrix
python -m pytest tests -q
python -m yinyo.cli diagnose --workspace ./workspace
python -m build
python scripts/verify_wheel.py --skip-build
python scripts/prepare_github_release.py --version v1.0.0-lite
```

For `v1.0.0-lite`, use [RELEASE_NOTES.md](RELEASE_NOTES.md) as the GitHub
Release body and attach only `dist/yinyo_agent-1.0.0rc1-py3-none-any.whl` and
`dist/yinyo_agent-1.0.0rc1.tar.gz`. Do not attach stale alpha artifacts,
runtime JSONL, smoke workspaces, raw env files, or unredacted Feishu payloads.
`prepare_github_release.py` writes `release-artifacts/v1.0.0-lite/RELEASE_BODY.md`,
`release-manifest.json`, and `SHA256SUMS.txt` for copy/paste and checksum review.

Clean wheel install evidence should include importing `yinyo`, `RuntimeConfig`,
`JsonlJobQueue`, release/smoke helpers, then confirming `yinyo serve --dry-run`
fails with redacted missing-config output when no secrets are provided. It should
also exercise installed CLI smoke plan/status and config-template commands.
`yinyo diagnose` should be used after a live smoke run to summarize runtime logs,
job status, event-store idempotency records, outbox failures, rejected webhooks,
runtime store lock state, and missing smoke scenarios.
It also reports service lifecycle status, ws event count, long-connection ACK
deadline misses, max ACK latency, and ACK deadline from `service_*` and
`ws_event_received` records. A failed `service_stop` is an operator alert.
`yinyo smoke preflight` should be used before the live run to verify local
configuration, writable stores, single-writer lock availability, SDK
availability, fresh evidence files, `ws_sdk_session_id` live provenance readiness,
and ACK deadline policy. If it reports
`fresh_evidence_files` as failed, run `yinyo smoke reset --config ./yinyo.env
--confirm-reset` before a fresh release attempt; use `--allow-existing-evidence`
only when intentionally continuing or diagnosing an existing run.
`yinyo smoke reset --confirm-reset` should be run after preflight and before a
fresh live smoke attempt so stale records cannot satisfy release evidence.
`yinyo smoke runbook` should be generated from the same config used by the live
service so the operator sequence, evidence path, 3+6 replay, diagnostics, and
`1.0.0` release gate stay aligned. It also embeds the current evidence
snapshot, missing chain layers, advanced live gaps, and the same
`operator_plan` emitted by `yinyo smoke status`.
`yinyo smoke wait` should run while the operator performs live Feishu actions;
it reports the missing smoke, runtime, job, event-store, and advanced live
evidence until the full 1.0 chain is complete or the timeout expires.
`yinyo smoke record-advanced` should be used after the corresponding real
Feishu workflow has run to record image understanding, long conversation,
memory supersession, Trace2Skill, DeepSeek usage, and partial-failure
references. Do not hand-edit `smoke_evidence.jsonl` for those scenarios.
The verifier checks the controlled recorder marker and reports
`advanced_source_missing` when advanced records were not produced by the command.
It also verifies the `yinyo.advanced_live_proof.v1` digest generated from the
redacted required fields, so copied or edited advanced records fail with
`advanced_proof_missing` or `advanced_proof_mismatch`.
Path-like advanced references are resolved locally when possible and reported
through `yinyo.advanced_ref_resolution.v1`; unresolved local paths or invalid
Trace2Skill validation files show up as `advanced_ref_unresolved`. Plain
redacted external tokens are still accepted as external references.
`yinyo smoke status` is the read-only triage view for an incomplete run; it
breaks missing evidence down by basic and advanced scenario layer and prints
operator next actions.
`yinyo smoke verify` is the compact smoke-evidence gate: default output is a
short operator summary, and `--json` returns the raw basic/advanced verification
object for automation.
`yinyo smoke bundle` should be run after live smoke to create the redacted
review artifact. The `1.0.0` ws release path requires `yinyo smoke bundle
--config ./yinyo.env --output ./workspace/smoke-bundle --handoff-dir
./workspace/runs --live-attestation-id <attestation-id>
--tenant-hash <sha256-tenant>` so
run-level `handoff.json` packets and operator live provenance travel with
runtime evidence. The command inherits `ws_sdk_session_id` from `yinyo.env`
and computes `feishu_app_id_hash` as `sha256(app_id)` from the same config.
`--ws-sdk-session-id` and `--feishu-app-id-hash` are optional and must match
`ws_sdk_session_id` and `sha256(app_id)` if provided. At least one handoff must
replay through `replay_handoff()` so the manifest reports
`handoff_ready_records > 0`. Share the bundle
directory, not raw runtime JSONL files. The bundle manifest records SHA-256 hashes for
every redacted evidence and handoff file plus a stable `bundle_digest`; rerun
bundle verification after transfer so file replacement, malformed handoff
packets, unreplayable handoff packets, digest drift, `yinyo.advanced_ref_attestation.v1` drift, missing
`yinyo.live_provenance.v1`, or placeholder provenance values are caught.
`python scripts/verify_release.py --bundle <dir>` should pass before that
bundle is shared for release review; it recomputes the evidence chain from the
redacted JSONL files instead of trusting `manifest.json` alone. For ws bundles,
it also recomputes the `live_provenance.ws_sdk_session_id` match against the
redacted `service_start` and `ws_transport_start` runtime log markers. The
bundle command inherits `ws_sdk_session_id` from the config when
`--ws-sdk-session-id` is omitted; if both are present, they must match. It also
computes `feishu_app_id_hash` from config `app_id`; `--feishu-app-id-hash`
must match `sha256(app_id)` if provided.
`python scripts/verify_release.py --target 1.0.0 --bundle <dir>` is the
shareable-evidence path for final R1 review; invalid bundles do not bypass the
live-smoke R1 blockers.
`python scripts/verify_release.py --target 1.0.0 --bundle <dir> --candidate
1.0.0` is the final tag/publish guard and should be the last local check before
creating `v1.0.0`. For a ws bundle, this guard requires redacted
`service_start`, `ws_transport_start`, and same-`event_key`
`ws_event_received` runtime logs for every basic smoke scenario with startup
config fields, `smoke_mode=false`, and ACK metrics, plus live provenance fields, not only
`transport=ws` metadata.
After this gate passes except for the expected alpha version/changelog blockers,
run `python scripts/prepare_release_metadata.py --version 1.0.0
--verified-bundle <dir>` as a dry run, then repeat with `--apply`. The apply
path refuses `1.0.0` without a verified ws bundle with replayable handoff
evidence. Re-run `python scripts/verify_release.py --target 1.0.0 --bundle
<dir> --candidate 1.0.0` after metadata promotion; only then create `v1.0.0`.
`python scripts/verify_secrets.py` must pass before sharing logs, publishing a
wheel, or tagging a release.
`yinyo serve` records `service_stop` when a transport exits normally or fails.
Failed exits log only `error_type`, not exception text, so shutdown evidence can
be shared without leaking secret-bearing error messages.

For `1.0.0`, the verifier also requires live smoke evidence to be present.
Use `python scripts/verify_release.py --target 1.0.0 --config <path>` when the
live deployment writes evidence outside the default `./workspace` directory.
Use `--json` on the same command to produce a machine-readable R1 readiness
audit that maps every `docs/spec.md` release criterion to evidence and blockers.
The GitHub Actions release workflow runs the same gate through
`.github/workflows/release.yml`; for `1.0.0`, pass `runtime_config_path` and
`smoke_bundle_path` when dispatching the workflow so CI verifies the same live
evidence used locally. The workflow routes bundle-backed dispatches through
`python scripts/verify_release.py --target <target> --bundle <dir>` instead of
the bare target gate. Do not publish artifacts that bypass it.
When dispatching a final `1.0.0` workflow, set `candidate=1.0.0` so CI runs the
same tag/publish guard.
The ws live smoke gate requires `text_message_reply`, `image_message_reply`,
`card_fallback`, and `duplicate_callback` records with `status=passed` and
`live=true`. HTTP fallback smoke additionally requires `url_verification`. For
`1.0.0`, those records must also be backed by matching `runtime.jsonl`,
`runtime_jobs.jsonl`, and `gateway_events.jsonl` evidence; handwritten smoke
records are not sufficient.
Local JSONL deployments must keep exactly one service process active. The
runtime lock at `runtime_lock_path` is the executable guard for that boundary.
If the previous local process crashed, preflight or service startup can recover
a stale same-host lock when the recorded PID no longer exists. Do not manually
delete locks from another host or from an owner string that cannot be parsed;
inspect the deployment first.
During live release smoke, temporarily set `smoke_mode=true` and send
`/yinyo-smoke card-fallback` to produce the deterministic card fallback path.
Then disable smoke mode, restart, collect the remaining basic scenarios, and
build the final bundle. The session verifier accepts only this immediately
preceding `smoke_mode=true` card probe before the latest `service_start`; every
other basic smoke record must come after the final `smoke_mode=false` restart.

---

## Smoke Evidence

Required scenarios live in [docs/deployment.md](docs/deployment.md).

Smoke evidence must be:

- Produced from real Feishu callbacks.
- Redacted before sharing.
- Linked to runtime logs through correlation ids.
- Linked to durable job and event-store records for `1.0.0`.
- Reset with `yinyo smoke reset --confirm-reset` before each fresh release run.
- Checked with `yinyo smoke status` when the chain is incomplete.
- Bundled through `yinyo smoke bundle` before release review.
- Kept out of git unless intentionally committed as sanitized fixtures.

---

## Incidents

Use [docs/incident-playbook.md](docs/incident-playbook.md). For production
readiness, review [docs/production-checklist.md](docs/production-checklist.md)
before tagging `1.0.0`.

---

## Versioning

External package versions follow [docs/versioning.md](docs/versioning.md).
Internal P-series gates are engineering acceptance states, not public versions.

---

## Cleanup

Do not commit:

- `.venv/`
- `.pytest_cache/`
- `yinyo_agent.egg-info/`
- live `workspace/` runtime data
- raw `.env` files
- unredacted `runtime.jsonl`, `gateway_events.jsonl`, or `smoke_evidence.jsonl`

