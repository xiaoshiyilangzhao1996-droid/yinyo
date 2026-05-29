<div align="center">

# YINYO v1.0.0-lite

"External Feishu testing line for the YINYO harness Agent."

![Version](https://img.shields.io/badge/version-1.0.0--lite-2ea043)
![Package](https://img.shields.io/badge/python-1.0.0rc1-blue)
![Status](https://img.shields.io/badge/status-external--testing-f59e0b)
![1.0](https://img.shields.io/badge/full%201.0-blocked%20by%20live%20evidence-d73a49)

</div>

YINYO `v1.0.0-lite` is the first public GitHub line for real Feishu testing.
It is intentionally not the full stable `v1.0.0` release.

[Assets](#assets) · [Install](#install) · [What Is Included](#what-is-included) · [Validation](#validation) · [1.0 Boundary](#10-boundary)

---

## Assets

Attach these two files to the GitHub Release:

- `yinyo_agent-1.0.0rc1-py3-none-any.whl`
- `yinyo_agent-1.0.0rc1.tar.gz`

The product version is `1.0.0-lite`. The Python package version is
`1.0.0rc1` because Python packaging requires PEP 440-compatible versions.

---

## Install

```bash
pip install yinyo-agent==1.0.0rc1
cp yinyo.env.example yinyo.env
yinyo serve --workspace ./workspace --profile local --transport ws
```

For source installs:

```bash
git clone https://github.com/<owner>/<repo>.git
cd <repo>
git checkout v1.0.0-lite
python -m venv .venv
python -m pip install -e ".[dev]"
```

---

## What Is Included

- Feishu long-connection runtime by default, with HTTP webhook fallback.
- DeepSeek-first model gateway with retry, fallback, usage, and cost telemetry.
- TemporalTree memory with supersession, durability filtering, provenance, and
  state-recovery checks.
- Trace2Skill promotion with replayed regression evidence.
- Versioned harness corpus and release matrix for the 3 product cores, 6
  behavioral traits, and ETCLOVG harness layers.
- Smoke, diagnostics, redaction, bundle, public-tree, secret, wheel, and release
  verification commands.
- GitHub tester guide: `docs/external-testing.md`.
- Public evidence matrix: `docs/release-evidence-matrix.md`.
- Benchmark method and limits: `docs/benchmarking.md`.

---

## Validation

The release was prepared with:

```bash
python -m pytest tests -q
python scripts/verify_release.py --target 1.0.0-lite --candidate 1.0.0-lite --json
python scripts/verify_public_tree.py
python scripts/verify_secrets.py
python -m build
python scripts/verify_wheel.py --skip-build
python scripts/prepare_github_release.py --version v1.0.0-lite
```

Expected local results:

- `356 passed`
- public tree verification passes
- secret scan passes
- wheel verification passes for `yinyo_agent-1.0.0rc1-py3-none-any.whl`
- lite candidate gate requires tag `v1.0.0-lite`

---

## 1.0 Boundary

Full `v1.0.0` remains blocked until a real Feishu long-connection evidence
bundle passes:

```bash
python scripts/verify_release.py --target 1.0.0 --bundle <bundle-dir> --candidate 1.0.0
```

That bundle must include redacted live evidence for:

- text message reply
- image message reply
- card fallback
- duplicate callback
- per-scenario `ws_event_received` ACK evidence
- image understanding
- long conversation
- memory supersession
- Trace2Skill promotion
- DeepSeek usage telemetry
- partial failure behavior
- replayable handoff packets and live provenance

Local replay is required, but it is not enough for full `v1.0.0`.

---

## Do Not Attach

Do not upload local runtime state or secrets:

- `.env`
- `.venv/`
- `workspace/`
- `runtime.jsonl`
- `runtime_jobs.jsonl`
- `gateway_events.jsonl`
- `smoke_evidence.jsonl`
- raw Feishu payloads or callback headers
- Feishu or DeepSeek secrets
