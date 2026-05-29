# Incident Playbook

Use this playbook when YINYO behaves incorrectly in a Feishu deployment.

---

## Severity

| Level | Examples | First action |
|-------|----------|--------------|
| SEV1 | Secret exposure, uncontrolled external action, repeated destructive tool attempt. | Stop service, rotate keys, preserve logs. |
| SEV2 | Replies wrong user/chat, duplicate responses, webhook storm, model failure loop. | Pause webhook or bot app, inspect correlation id. |
| SEV3 | Formatting issue, delayed reply, isolated failed job. | Keep service running, inspect job/runtime logs. |

---

## Evidence To Preserve

Collect only redacted copies:

- `runtime.jsonl`
- `runtime_jobs.jsonl`
- `gateway_events.jsonl`
- `smoke_evidence.jsonl`
- `runs/<run_id>/manifest.json`
- `runs/<run_id>/evidence.jsonl`
- relevant sanitized Feishu callback metadata

Never paste raw app secrets, verify tokens, tenant tokens, API keys, or private
message content into public issues.

---

## Triage Steps

1. Identify the `correlation_id` from `runtime.jsonl`.
2. Find the matching job in `runtime_jobs.jsonl`.
3. Find the `run_id` from the outbox delivery log or job result.
4. Open `runs/<run_id>/manifest.json`.
5. Inspect `runs/<run_id>/evidence.jsonl` for blocked tools, API errors, or missing verification.
6. Check `gateway_events.jsonl` to confirm whether duplicate suppression ran.
7. If secrets may have leaked, rotate Feishu and model credentials before deeper debugging.

---

## Secret Exposure

Immediate actions:

1. Stop `yinyo serve`.
2. Rotate `FEISHU_APP_SECRET`, `FEISHU_VERIFY_TOKEN`, and model API keys.
3. Remove unredacted logs from shared locations.
4. Run tests covering redaction:

```bash
python -m pytest tests/test_governance.py tests/test_p4_service.py -q
```

5. Record a post-incident note with the cause and prevention.

---

## Duplicate Replies

Check:

- Whether the same Feishu `uuid`, `event_id`, or `message_id` appears more than once.
- Whether `gateway_events.jsonl` contains the event key.
- Whether multiple service processes share the same `gateway_events.jsonl`.

Current alpha supports durable local idempotency. Multi-process deployments must
share the same event store or use an external queue/store adapter.

---

## Failed Jobs

Check `runtime_jobs.jsonl`:

- `status=failed`
- `error`
- `payload.event_key`

Then use the same event key as `correlation_id` in `runtime.jsonl`.

---

## Recovery

After mitigation:

```bash
python scripts/verify_release.py
python scripts/replay_scenarios.py
python -m pytest tests -q
```

For release-impacting incidents, do not tag `1.0.0` until the incident has a
regression test or replay fixture.
