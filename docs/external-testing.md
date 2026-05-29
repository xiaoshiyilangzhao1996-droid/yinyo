<div align="center">

# External Testing

"Run YINYO against a real Feishu app and return evidence, not secrets."

![Status](https://img.shields.io/badge/status-lite-2ea043)
![Scope](https://img.shields.io/badge/scope-live--feishu-blue)
![Release](https://img.shields.io/badge/1.0-needs%20bundle-d73a49)

</div>

Guide for GitHub users validating YINYO with a real Feishu app.

[Install](#install) · [Configure](#configure) · [Run](#run) · [Collect Evidence](#collect-evidence) · [Share Results](#share-results) · [Do Not Share](#do-not-share)

---

## Install

Use a fresh virtual environment on a trusted local machine:

```bash
git clone https://github.com/xiaoshiyilangzhao1996-droid/yinyo.git
cd yinyo
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

For package-only testing after a release is published:

```bash
python -m pip install yinyo-agent
```

The current public line is `1.0.0-lite` with Python package version
`1.0.0rc1`. It is suitable for external live testing, but it is not the full
stable `1.0.0` release.

---

## Configure

Create a local config file and keep it out of git:

```bash
python -m yinyo.cli config template --live-smoke > yinyo.env
```

Fill in at least:

```env
workspace=./workspace
profile=local
transport=ws
app_id=cli_xxx
app_secret=xxx
deepseek_api_key=sk-xxx
ws_sdk_session_id=<redacted-session-id-you-choose-for-this-run>
```

Use a Feishu self-built app with event subscriptions and callback long
connection enabled. HTTP webhook mode is supported as fallback coverage, but
the `1.0.0` release path requires `transport=ws`.

Run local checks before starting the service:

```bash
python -m yinyo.cli serve --config ./yinyo.env --dry-run
python -m yinyo.cli smoke runbook --config ./yinyo.env
python -m yinyo.cli smoke preflight --config ./yinyo.env
```

If preflight reports existing evidence files and this is a fresh attempt:

```bash
python -m yinyo.cli smoke reset --config ./yinyo.env --confirm-reset
```

---

## Run

Start the service and keep the terminal open:

```bash
python -m yinyo.cli serve --config ./yinyo.env
```

From Feishu, exercise the real app:

| Scenario | Operator action |
|---|---|
| Text message reply | Send a normal text message to the bot. |
| Image message reply | Send an image to the bot and confirm a reply or graceful vision fallback. |
| Duplicate callback | Re-send or replay the same callback only if your test setup supports it. |
| Card fallback | Temporarily set `smoke_mode=true`, restart, send `/yinyo-smoke card-fallback`, then set `smoke_mode=false` and restart before final collection. |

Watch progress in another terminal:

```bash
python -m yinyo.cli smoke status --config ./yinyo.env
python -m yinyo.cli smoke wait --config ./yinyo.env
```

---

## Collect Evidence

After the corresponding real Feishu workflow has run, record advanced evidence
through the supported command. Do not hand-edit `smoke_evidence.jsonl`.

```bash
python -m yinyo.cli smoke record-advanced --config ./yinyo.env --scenario image_understanding --image-ref <redacted-image-ref>
python -m yinyo.cli smoke record-advanced --config ./yinyo.env --scenario long_conversation --transcript-ref <redacted-transcript-ref>
python -m yinyo.cli smoke record-advanced --config ./yinyo.env --scenario memory_supersession --memory-ref <redacted-memory-ref>
python -m yinyo.cli smoke record-advanced --config ./yinyo.env --scenario trace2skill_promotion --failure-trace-ref <redacted-failure-trace-ref> --skill-ref <redacted-skill-ref> --regression-result-ref <redacted-regression-result-ref> --promotion-status proven --post-promotion-run-ref <redacted-run-ref>
python -m yinyo.cli smoke record-advanced --config ./yinyo.env --scenario deepseek_usage --usage-ref <redacted-usage-ref>
python -m yinyo.cli smoke record-advanced --config ./yinyo.env --scenario partial_failure --failure-ref <redacted-failure-ref>
```

Build a redacted bundle:

```bash
python -m yinyo.cli smoke bundle --config ./yinyo.env --output ./workspace/smoke-bundle --handoff-dir ./workspace/runs --live-attestation-id <attestation-id> --tenant-hash <sha256-tenant>
python scripts/verify_release.py --bundle ./workspace/smoke-bundle
python scripts/verify_release.py --target 1.0.0 --bundle ./workspace/smoke-bundle
```

The bundle verifier recomputes the evidence chain from redacted files. It does
not trust `manifest.json` alone.
It also verifies `live_provenance.ws_sdk_session_id` against the redacted
`service_start` and `ws_transport_start` runtime markers. The bundle command
inherits `ws_sdk_session_id` from `yinyo.env`; if `--ws-sdk-session-id` is
provided, it must match the config value. The command computes
`feishu_app_id_hash` as `sha256(app_id)` from the same config; if
`--feishu-app-id-hash` is provided, it must match `sha256(app_id)`.

---

## Share Results

Open a GitHub issue or release-test report with:

- YINYO version or commit SHA.
- Python version and OS.
- Feishu transport mode, normally `ws`.
- Output of `python scripts/verify_release.py --bundle <bundle-dir>`.
- Output of `python scripts/verify_release.py --target 1.0.0 --bundle <bundle-dir>`.
- The redacted `smoke-bundle` directory if it contains no secrets and your
  organization allows sharing it.

Passing external reports can support a later `v1.0.0` release only after the
strict candidate guard passes:

```bash
python scripts/verify_release.py --target 1.0.0 --bundle <bundle-dir> --candidate 1.0.0
```

---

## Do Not Share

Never post these values in GitHub issues, chat, screenshots, or release notes:

- Feishu `app_secret`, tenant token, user token, or raw callback headers.
- DeepSeek API keys or proxy keys.
- Raw user messages, private images, private file URLs, or private meeting data.
- Unredacted `runtime.jsonl`, `gateway_events.jsonl`, `runtime_jobs.jsonl`, or
  `smoke_evidence.jsonl`.
- A raw `yinyo.env`.

Run the secret scan before sharing any artifact from the repo:

```bash
python scripts/verify_secrets.py
```
