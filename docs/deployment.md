# Deployment

YINYO is a Feishu-only agent service. The default lite deployment path uses
Feishu's official long-connection server SDK. HTTP webhook mode remains
available for hosted callback deployments.

---

## Requirements

- Python 3.11, 3.12, or 3.13
- A Feishu app with event callbacks enabled
- DeepSeek API key
- For long-connection mode: a Feishu self-built app with event subscription
  enabled and callback long connection enabled.
- For HTTP mode: a reachable webhook URL that forwards to `yinyo serve`.

---

## Configuration

Copy the versioned example or generate a local config file outside version
control, then fill in secrets on the deployment machine:

```bash
cp yinyo.env.example ./yinyo.env
```

```bash
yinyo config template > ./yinyo.env
```

The generated template intentionally leaves app secrets and API keys empty.
`verify_token` is required for HTTP webhook callbacks, but optional for the
default Feishu long-connection (`ws`) transport. For a live release smoke run,
generate the smoke-oriented template:

```bash
yinyo config template --live-smoke > ./yinyo.env
```

Equivalent minimal config:

```env
workspace=./workspace
profile=local
transport=ws
host=0.0.0.0
port=8080
app_id=cli_xxx
app_secret=xxx
deepseek_api_key=sk-xxx
```

Optional:

```env
verify_token=xxx  # Required only when transport=http.
deepseek_base_url=https://api.deepseek.com
default_model=deepseek-v4-flash
model_timeout_seconds=120
model_retry_count=1
model_retry_backoff_seconds=0.5
ack_deadline_seconds=3
max_steps=50
job_max_workers=4
event_store_path=./workspace/gateway_events.jsonl
job_store_path=./workspace/runtime_jobs.jsonl
log_path=./workspace/runtime.jsonl
smoke_evidence_path=./workspace/smoke_evidence.jsonl
runtime_lock_path=./workspace/yinyo_runtime.lock
```

For a live release smoke run only, enable the controlled smoke probe:

```env
smoke_mode=true
```

With smoke mode enabled, send `/yinyo-smoke card-fallback` to the bot to force
a text fallback record through the normal gateway, outbox, job, and evidence
chain. Keep `smoke_mode` unset or `false` for normal operation. `profile=production`
rejects `smoke_mode=true` during config validation.

Do not commit this file.

---

## Validate

```bash
yinyo serve --config ./yinyo.env --dry-run
yinyo smoke runbook --config ./yinyo.env
yinyo smoke preflight --config ./yinyo.env
```

The dry run prints redacted config and exits. The runbook prints the exact
operator sequence for live Feishu smoke, local 3+6 evidence replay, diagnostics,
and the `1.0.0` release gate; it also embeds the current evidence snapshot,
missing chain layers, advanced live gaps, and `operator_plan` from the same
status verifier used by `yinyo smoke status`. The preflight performs local, non-network checks
for required config, writable runtime paths, fresh evidence files, long-connection SDK availability
and callback handler contract, `ws_sdk_session_id` live provenance readiness, single-writer lock availability, and ACK deadline policy. It refuses
non-empty smoke/runtime/job/event-store files by default so a fresh release run cannot accidentally
reuse stale records; pass `--allow-existing-evidence` only for explicit continuation or diagnostics. None of these
commands must print raw app secrets, verify tokens, or API keys.

---

## Diagnose

After the service has processed callbacks, summarize local runtime health:

```bash
yinyo diagnose --config ./yinyo.env
yinyo diagnose --config ./yinyo.env --json
```

The diagnostic report reads `runtime.jsonl`, `runtime_jobs.jsonl`,
`gateway_events.jsonl`, `smoke_evidence.jsonl`, and `runtime_lock_path`. It
reports whether the local runtime store lock is available or currently held by
the running service. Text and JSON output include service lifecycle status, ws
event count, ACK deadline misses, max ACK latency, and ACK deadline. It returns
a non-zero exit code when runtime jobs fail, the service exits with failure,
webhooks are rejected, outbox delivery fails, event-store idempotency records
are missing, ACK deadlines are missed, or required live smoke evidence is
missing.

---

## Start

Recommended long-connection mode:

```bash
yinyo serve --config ./yinyo.env
```

Long-connection runtime notes:

- Use a Feishu self-built app. Long connection is not the generic marketplace
  app path.
- Keep event acknowledgment under 3 seconds. YINYO returns from the gateway
  before the agent run finishes and records `ack_latency_ms`,
  `ack_deadline_ms`, and `ack_within_deadline` in `runtime.jsonl`.
- Do not assume every connected client receives every event. Multiple
  long-connection clients form a cluster-style deployment, so local JSONL
  idempotency/job stores require a single active worker. `runtime_lock_path`
  enforces that boundary for local stores; use an external shared store before
  running more than one writer.

Official references:

- Feishu server SDK overview:
  <https://open.feishu.cn/document/server-docs/server-side-sdk>
- Python server SDK event handling:
  <https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/server-side-sdk/python--sdk/handle-events>
- Long-connection event configuration:
  <https://open.feishu.cn/document/server-docs/event-subscription-guide/event-subscription-configure-/request-url-configuration-case>

HTTP webhook fallback:

```bash
yinyo serve --config ./yinyo.env --transport http
```

The service writes:

| File | Purpose |
|------|---------|
| `runtime.jsonl` | Structured gateway/outbox logs. |
| `gateway_events.jsonl` | Durable Feishu event idempotency store. |
| `runtime_jobs.jsonl` | Durable runtime job lifecycle records. |
| `smoke_evidence.jsonl` | Redacted smoke evidence records. |
| `yinyo_runtime.lock` | Exclusive process lock for local JSONL runtime stores. |
| `runs/*/manifest.json` | Agent run manifests with correlation ids. |
| `runs/*/evidence.jsonl` | Tool evidence records with correlation ids. |

Runtime JSONL files are appended through a shared thread-safe writer inside one
service process, so concurrent gateway workers do not create partial JSON
records. `yinyo serve` holds `runtime_lock_path` while the service is running,
so a second local process cannot write the same event/job/log stores. For
multi-process deployments, replace the local JSONL files with an external
shared queue/store adapter.
If a local service crashes and leaves a lock from the same host whose PID no
longer exists, the next preflight or service start recovers that stale lock
automatically. Locks from another host or with an unparseable owner remain
blocking and should be inspected by an operator.

---

## Smoke Evidence

Before beta or 1.0, collect redacted evidence for the selected transport. The
primary `1.0.0` path is `transport=ws`; HTTP callback proof remains fallback
coverage.

- `url_verification`: Feishu URL verification for `transport=http` only.
- `text_message_reply`: text message receive and reply.
- `image_message_reply`: image message receive and vision fallback.
- `card_fallback`: Card send fallback to text.
- `duplicate_callback`: duplicate callback suppression.

For `1.0.0`, also collect advanced live records in the same
`smoke_evidence.jsonl` file:

- `image_understanding`: include `image_ref` or `run_id`.
- `long_conversation`: include `transcript_ref` or `run_id`.
- `memory_supersession`: include `memory_ref` or `run_id`.
- `trace2skill_promotion`: include `failure_trace_ref`, `skill_ref`,
  `regression_result_ref` or legacy `regression_ref`, `promotion_status`, and
  `post_promotion_run_ref`; `promotion_status` must be `proven` or `stable`.
- `deepseek_usage`: include `model_usage` or `usage_ref`.
- `partial_failure`: include `failure_ref` or `run_id`.

Use the controlled recorder rather than hand-editing JSONL after the service is
running and the real Feishu workflow has produced the redacted references. The
verifier checks the controlled recorder marker; handwritten advanced records do
not satisfy the `1.0.0` gate.

The `card_fallback` scenario can be produced deterministically during release
smoke by temporarily setting `smoke_mode=true` and sending
`/yinyo-smoke card-fallback` to the bot. The command is treated as normal user
text when smoke mode is disabled. Change the config, restart the service with
`smoke_mode=true`, collect the card-fallback evidence, then change it back to
`false` and restart before collecting the remaining live scenarios and building
the final bundle. The session verifier treats only this immediately preceding
`smoke_mode=true` card probe as valid before the latest `service_start`; every
other basic smoke record must be collected after the final `smoke_mode=false`
restart.

Evidence must use real platform callbacks but must not contain raw tokens,
message content secrets, or API keys. For `1.0.0`, the release verifier checks
the full evidence chain, not just `smoke_evidence.jsonl`: smoke records must be
backed by `runtime.jsonl`, `runtime_jobs.jsonl`, and `gateway_events.jsonl`
records with matching event keys or correlation ids.

Verify the evidence:

```bash
yinyo smoke runbook --config ./yinyo.env
yinyo smoke plan --path ./workspace/smoke_evidence.jsonl
yinyo smoke preflight --config ./yinyo.env
yinyo smoke reset --config ./yinyo.env --confirm-reset
yinyo serve --config ./yinyo.env
```

Before running preflight, set `ws_sdk_session_id` in `yinyo.env`. The bundle
command inherits `ws_sdk_session_id` from the same config when
`--ws-sdk-session-id` is omitted.
If both are set, they must match. The verified bundle cross-checks that
manifest live provenance against `service_start` and `ws_transport_start`
runtime markers. The bundle command also computes `feishu_app_id_hash` as
`sha256(app_id)` from config; `--feishu-app-id-hash` is optional and must match
`sha256(app_id)` if provided.

Keep the service process running while you perform the real Feishu text, image,
duplicate-callback, and card-fallback actions from the Feishu app. In another
terminal, record advanced evidence and wait for the chain:

`yinyo smoke record-advanced` adds a `yinyo.advanced_live_proof.v1` digest over
the redacted required fields. Missing or mismatched advanced proofs block
`1.0.0` readiness and redacted bundle verification.
Path-like advanced refs are also resolved locally when possible. A
`validation_ref`, `regression_result_ref`, `skill_ref`, `usage_ref`,
`failure_ref`, or `run_id` that looks like a local file must exist and match the
expected schema; unresolved refs surface as `advanced_ref_unresolved`. Plain
redacted external tokens remain valid external references.
Use a non-path redacted token only when the source artifact lives in an external
system. If a ref looks like a local path, the file must exist before
`record-advanced` writes the evidence.

```bash
yinyo smoke record-advanced --config ./yinyo.env --scenario image_understanding --image-ref <redacted-image-ref>
yinyo smoke record-advanced --config ./yinyo.env --scenario long_conversation --transcript-ref <redacted-transcript-ref>
yinyo smoke record-advanced --config ./yinyo.env --scenario memory_supersession --memory-ref <redacted-memory-ref>
yinyo smoke record-advanced --config ./yinyo.env --scenario trace2skill_promotion --failure-trace-ref <redacted-failure-trace-ref> --skill-ref <redacted-skill-ref> --regression-result-ref <redacted-regression-result-ref> --promotion-status proven --post-promotion-run-ref <redacted-run-ref>
yinyo smoke record-advanced --config ./yinyo.env --scenario deepseek_usage --usage-ref <redacted-usage-ref>
yinyo smoke record-advanced --config ./yinyo.env --scenario partial_failure --failure-ref <redacted-failure-ref>
yinyo smoke wait --config ./yinyo.env
yinyo smoke status --config ./yinyo.env
yinyo smoke verify --transport ws --path ./workspace/smoke_evidence.jsonl
yinyo smoke verify --transport ws --path ./workspace/smoke_evidence.jsonl --json
yinyo smoke bundle --config ./yinyo.env --output ./workspace/smoke-bundle --handoff-dir ./workspace/runs --live-attestation-id <attestation-id> --tenant-hash <sha256-tenant>
python scripts/verify_release.py --bundle ./workspace/smoke-bundle
python scripts/replay_scenarios.py --matrix
python scripts/verify_release.py --target 1.0.0 --bundle ./workspace/smoke-bundle
python scripts/verify_release.py --target 1.0.0 --bundle ./workspace/smoke-bundle --candidate 1.0.0
python scripts/prepare_release_metadata.py --version 1.0.0 --verified-bundle ./workspace/smoke-bundle
python scripts/prepare_release_metadata.py --version 1.0.0 --verified-bundle ./workspace/smoke-bundle --apply
python scripts/verify_release.py --target 1.0.0 --bundle ./workspace/smoke-bundle --candidate 1.0.0
python scripts/verify_release.py --target 1.0.0 --config ./yinyo.env
```

The wait command polls `smoke_evidence.jsonl`, `runtime.jsonl`,
`runtime_jobs.jsonl`, and `gateway_events.jsonl` until the full 1.0 evidence
chain is present, including advanced live records, or the timeout expires. Use
`yinyo smoke status` during or after the run when you need a read-only view of
which basic or advanced scenario layer is still missing and what operator action
should happen next. `yinyo smoke verify` prints a short operator summary by
default; use `--json` when CI or another tool needs the raw basic/advanced
verification object. The bundle command writes redacted
copies of `runtime.jsonl`,
`runtime_jobs.jsonl`, `gateway_events.jsonl`, and `smoke_evidence.jsonl`, plus
redacted `runs/*/handoff.json` packets when `--handoff-dir` is passed, live
provenance when the attestation/hash flags are passed, and
`chain.json`, `advanced.json`, `diagnostics.json`, and `manifest.json`. Its text
output lists `chain_missing`, `advanced_missing`, `advanced_field_missing`,
`advanced_source_missing`, and `diagnostics_alerts` so the release blocker is
visible without opening the manifest. Use that directory as the release review
artifact, not raw runtime files. `manifest.json` includes SHA-256 hashes for
each redacted evidence and handoff file plus a stable `bundle_digest` for the
whole bundle, and bundle verification rejects replaced files, malformed handoff
packets, handoffs that fail `replay_handoff()` into `yinyo.handoff_resume.v1`,
digest mismatches, or `yinyo.advanced_ref_attestation.v1` drift. For ws release
bundles, `manifest.handoffs.ready_records` and
`frontier_readiness.handoff_ready_records` must be greater than zero.
`python scripts/verify_release.py --bundle <bundle-dir>` verifies that the
shared redacted bundle is complete, internally consistent, still free of obvious
secret patterns, and that its redacted JSONL files recompute the same evidence
chain as `chain.json`.
`python scripts/verify_release.py --target 1.0.0 --bundle <bundle-dir>` uses a
verified bundle as the shareable proof for R1-03, R1-07, and the advanced
R1-08 through R1-11 evidence gates. An invalid or basic-only bundle does not
satisfy those release gates.
`python scripts/verify_release.py --target 1.0.0 --bundle <bundle-dir>
--candidate 1.0.0` is the final tag/publish guard. It rejects `v1.0.0` if the
target version, release audit, live smoke evidence, and `transport=ws`
long-connection bundle metadata do not agree. It also requires
`yinyo.live_provenance.v1` with a redacted operator attestation id, Feishu app
hash, tenant hash, and ws SDK session id, so synthetic local fixtures cannot
stand in for live Feishu evidence. The bundle verifier cross-checks
`live_provenance.ws_sdk_session_id` against `runtime.redacted.jsonl`, the
redacted runtime log, `service_start` and `ws_transport_start`
`ws_sdk_session_id` markers instead of trusting the manifest alone. HTTP smoke evidence remains the
fallback-path proof, not the primary `1.0.0` release proof. A final ws bundle
must also contain at least one replayable run-level `handoff.json`, a redacted
`service_start` runtime log with startup config fields and `smoke_mode=false`, plus
`ws_transport_start` and same-`event_key` `ws_event_received` records for every
basic smoke scenario with `ack_latency_ms`, `ack_deadline_ms`, and
`ack_within_deadline=true`. The ws bundle does not
require an HTTP `url_verification` smoke record.
The attestation id should be a redacted, durable operator record such as a
release checklist id, test-run ticket, or meeting-note id that the release owner
can look up later; placeholders are rejected.

After the bundle gate is otherwise green, run `python
scripts/prepare_release_metadata.py --version 1.0.0 --verified-bundle
<bundle-dir>` as a dry run, then repeat with `--apply`. The script refuses
`1.0.0 --apply` unless that bundle verifies as a ws long-connection bundle with
replayable handoff evidence. Re-run the `--candidate 1.0.0` gate after metadata
promotion.

Run `yinyo smoke reset --config ./yinyo.env --confirm-reset` immediately before
a fresh live smoke attempt to avoid stale records satisfying part of the gate.
The reset command only truncates `smoke_evidence.jsonl`, `runtime.jsonl`,
`runtime_jobs.jsonl`, and `gateway_events.jsonl`; it does not delete historical
`runs/*` artifacts.

For `1.0.0`, prefer `python scripts/verify_release.py --target 1.0.0 --config
./yinyo.env` over passing only `--smoke-path`. The config-driven gate verifies
the smoke, runtime log, job store, and event-store paths as one evidence set.

---

## Current Limits

- Long-connection mode requires Feishu's official `lark-oapi` server SDK and a
  self-built Feishu app with callback long connection enabled.
- Feishu event acknowledgment must stay under the configured
  `ack_deadline_seconds` and must not exceed 3 seconds in `ws` mode.
- Event idempotency is durable.
- Runtime jobs execute in-process but write durable JSONL lifecycle records.
  Runtime logs, smoke evidence, event ids, and job records use thread-safe
  append within one process. `runtime_lock_path` enforces the single-worker
  boundary for local JSONL stores. For multi-process production deployments,
  add an external shared queue/store adapter before claiming beta readiness.
- Live smoke evidence is required before public `1.0.0`.
