<div align="center">

# YINYO

**A lightweight Harness Agent for Feishu and DeepSeek workflows**

*Feishu as the interface · DeepSeek as the model path · memory, evidence, and self-improvement built in*

![Status](https://img.shields.io/badge/status-lite-2ea043)
![Version](https://img.shields.io/badge/version-1.0.0--lite-2ea043)
![Package](https://img.shields.io/badge/python-1.0.0rc1-blue)
![Surface](https://img.shields.io/badge/surface-feishu-2ea043)
![Model](https://img.shields.io/badge/model-deepseek-f59e0b)
![Tests](https://img.shields.io/badge/tests-356%20local-2ea043)

**[English](README.md) · [中文](README.zh-CN.md) · [Getting Started 中文](docs/getting-started.zh-CN.md)**

</div>

YINYO puts a verifiable, memory-backed, self-improving Agent into Feishu workflows. Users talk to a Feishu bot; YINYO receives events, calls DeepSeek, keeps durable memory, records runtime evidence, and turns repeated failures into reusable skills.

> Design philosophy: **do not start as a universal platform; make real Feishu work first.**

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Product Constitution](#product-constitution)
- [Demo Scenarios](#demo-scenarios)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Architecture](#architecture)
- [Self-Improvement](#self-improvement)
- [Comparison](#comparison)
- [Evaluation](#evaluation)
- [Roadmap](#roadmap)
- [Community](#community)
- [Release Status](#release-status)
- [License](#license)

---

## Overview

YINYO is a Feishu-first harness Agent product benchmarked against Hermes and OpenClaw design expectations. It is not a generic chatbot wrapper and not a broad multi-platform gateway. It uses Feishu as the first user surface and DeepSeek as the first model assumption, then combines runtime orchestration, memory evolution, Trace2Skill, observability, and release gates into one deployable product line.

It is built for:

- users who want an Agent inside Feishu chats,
- teams testing Feishu office-workflow automation,
- developers studying memory evolution, Trace2Skill, and evidence-backed release gates,
- users who want another Agent to install and operate YINYO from docs.

---

## Key Features

| Feature | Description |
|---|---|
| **Feishu-native surface** | Long-connection `ws` transport, text/image handling, replies, card fallback, and duplicate-event protection. |
| **DeepSeek-first path** | DeepSeek defaults with timeout, retry, fallback, usage telemetry, and cost estimates. |
| **Durable memory** | TemporalTree facts evolve through supersession instead of stale-note accumulation. |
| **Self-improvement** | Trace2Skill extracts repeated failures into skills and promotes them only after replay evidence. |
| **Evidence-backed runtime** | Runtime logs, jobs, event store, smoke evidence, diagnostics, and release gates are first-class. |
| **Tight scope** | Feishu + DeepSeek first; no platform sprawl into WeChat, QQ, DingTalk, desktop pets, or generic UI shells. |

---

## Product Constitution

YINYO keeps three product cores: Less is more, Borrow what works, and DeepSeek adapted.

It also keeps six behavioral traits: curiosity, reliability, fact hygiene, multidisciplinary thinking, negative capability, and low ego with high drive. These traits are not slogans; they map to [docs/release-evidence-matrix.md](docs/release-evidence-matrix.md).

---

## Demo Scenarios

| Scenario | User asks | YINYO does |
|---|---|---|
| Work summary | "Turn this meeting note into conclusions and action items." | Produces structured conclusions, risks, and next steps. |
| Clarification | "Handle yesterday's issue." | Admits missing context and asks for the needed details. |
| Image input | User sends a screenshot and asks what matters. | Attempts image understanding or returns a clear fallback when vision is unavailable. |
| Long conversation | User iterates goals, constraints, and feedback. | Keeps relevant context and revises the plan. |
| Failure boundary | User asks for private data the bot cannot access. | Refuses overreach and suggests a safe alternative. |
| Release validation | Real Feishu usage produces feedback. | Helps maintainers decide whether full `1.0.0` evidence is ready. |

For product-level Feishu acceptance tasks, see [docs/feishu-user-acceptance.zh-CN.md](docs/feishu-user-acceptance.zh-CN.md).

---

## Quick Start

Recommended Python versions: 3.11, 3.12, or 3.13.

For a step-by-step Chinese guide covering install, DeepSeek API key setup, Feishu app setup, and first run, use:

[docs/getting-started.zh-CN.md](docs/getting-started.zh-CN.md)

Developer install:

```bash
git clone https://github.com/xiaoshiyilangzhao1996-droid/yinyo.git
cd yinyo
python -m venv .venv
python -m pip install -U pip
python -m pip install -e ".[dev]"
python -m yinyo.cli config template > yinyo.env
```

Fill `yinyo.env` with `transport=ws`, your Feishu App ID and App Secret, and your DeepSeek API key. Keep the raw values local.

Check config:

```bash
yinyo serve --config ./yinyo.env --dry-run
```

Start:

```bash
yinyo serve --config <path-to-yinyo.env>
```

---

## Usage

### Feishu Bot

1. Create a Feishu self-built app.
2. Add bot capability.
3. Enable event subscription and long connection.
4. Subscribe to P2 IM message receive events.
5. Enable message send/reply permissions.
6. Fill `yinyo.env`.
7. Run `yinyo serve --config <path-to-yinyo.env>`.

### CLI

| Command | Purpose |
|---|---|
| `yinyo config template` | Generate a local config template. |
| `yinyo serve --config <config>` | Start the Feishu Agent service. |
| `yinyo diagnose --config ./yinyo.env` | Inspect runtime health. |
| `yinyo smoke status --config ./yinyo.env` | Inspect release-evidence gaps. |
| `python scripts/replay_scenarios.py --matrix` | Replay the local harness scenario matrix. |

---

## Architecture

YINYO solves Feishu workflows through **Feishu events x DeepSeek gateway x memory evolution x evidence chain x release gate**.

### 1. Runtime Gateway

Feishu callbacks are normalized, deduplicated, acknowledged quickly, queued as jobs, delivered through outbox, and recorded into runtime logs.

### 2. DeepSeek-first Model Gateway

Model calls carry timeout, retry, fallback, usage, call count, and cost metadata so behavior can be diagnosed later.

### 3. TemporalTree Memory

New facts can supersede old facts. Search excludes superseded facts while keeping an audit trail.

### 4. Trace2Skill

Repeated failures can become skills only after regression replay proves the fix.

### 5. Evidence & Release Gate

Claims map to tests, scenario replay, smoke evidence, redacted bundles, and release verifier checks. Full `1.0.0` requires real Feishu live evidence.

---

## Self-Improvement

```text
[Real task]
   |
   v
[Runtime and failure trace] -> logs / evidence
   |
   v
[Reusable pattern] -> Trace2Skill
   |
   v
[Replay validation] -> regression fixture
   |
   v
[Promoted skill] -> reused in similar tasks
```

YINYO does not treat a written summary as learning. It expects trace evidence, a skill artifact, replay validation, and promotion status.

---

## Comparison

| Dimension | YINYO | GenericAgent | Hermes / OpenClaw |
|---|---|---|---|
| First surface | Feishu bot | Local computer, browser, desktop and IM frontends | Broader agent / harness systems |
| Product shape | Feishu + DeepSeek product line | Minimal self-evolving toolbox | Larger framework ecosystems |
| Memory | TemporalTree supersession | Layered memory and SOPs | Implementation-dependent |
| Evolution | Trace2Skill plus regression replay | Task experience crystallizes into skills | Varies |
| Release stance | Release gates plus live evidence | Demo and technical-report driven | Project-specific |
| Current maturity | `1.0.0-lite`, waiting for live Feishu evidence | Rich demos and community assets | Design references |

YINYO does not claim to be more mature than those projects. Its difference is the focused product path: Feishu workflows, DeepSeek assumptions, evidence chains, and release gates in one repo.

---

## Evaluation

Current reproducible evidence:

- `356` local tests.
- `scripts/replay_scenarios.py --matrix` covers 3 product cores, 6 behavioral traits, and ETCLOVG harness layers.
- `scripts/verify_release.py --target 1.0.0-lite --candidate 1.0.0-lite` gates the lite line.
- `scripts/verify_public_tree.py` keeps runtime data, build outputs, secrets, workspaces, and caches out of the public repo.

```bash
python scripts/replay_scenarios.py --matrix
python scripts/verify_release.py --target 1.0.0-lite --candidate 1.0.0-lite
python scripts/verify_secrets.py
python scripts/verify_public_tree.py
python -m pytest tests -q
```

See [docs/release-evidence-matrix.md](docs/release-evidence-matrix.md).

---

## Roadmap

| Stage | Goal |
|---|---|
| `v1.0.0-lite` | Public GitHub repo, install path, DeepSeek config, Feishu setup, local release gate. |
| Real Feishu validation | Collect real text, image, card fallback, duplicate event, long conversation, and failure feedback. |
| Verified ws bundle | Maintainers prepare a redacted live evidence bundle. |
| Full `v1.0.0` | Publish only after verified live evidence and candidate guard pass. |

See [docs/roadmap.md](docs/roadmap.md) and [docs/versioning.md](docs/versioning.md).

---

## Community

- Repository: [xiaoshiyilangzhao1996-droid/yinyo](https://github.com/xiaoshiyilangzhao1996-droid/yinyo)
- Issues: [GitHub Issues](https://github.com/xiaoshiyilangzhao1996-droid/yinyo/issues)
- Chinese guide: [docs/getting-started.zh-CN.md](docs/getting-started.zh-CN.md)
- Feishu acceptance guide: [docs/feishu-user-acceptance.zh-CN.md](docs/feishu-user-acceptance.zh-CN.md)

Do not share API keys, App Secrets, raw `yinyo.env`, private chats, or raw `workspace/` runtime files.

---

## Release Status

Current external version: `1.0.0-lite`

Python package version: `1.0.0rc1`

| Surface | Value |
|---|---|
| Product version | `1.0.0-lite` |
| Python package | `1.0.0rc1` |
| Stable `1.0.0` | blocked until verified Feishu live evidence |

`v1.0.0-lite` is the public line for download and real Feishu validation. It is not the full stable `v1.0.0`.

Full `1.0.0` is blocked until live Feishu smoke evidence proves the same product path in a real app. The public release boundary is intentionally strict: smoke records must be backed by runtime logs, durable job records, event idempotency records, and the single-writer runtime lock. The primary candidate path requires `transport=ws`, redacted runtime log evidence containing `service_start`, `ws_transport_start`, same-event-key `ws_event_received`, and ACK metrics.

For the full candidate gate, maintainers should follow [docs/external-testing.md](docs/external-testing.md), [docs/deployment.md](docs/deployment.md), [docs/production-checklist.md](docs/production-checklist.md), and [RELEASE_NOTES.md](RELEASE_NOTES.md). The evidence bundle must include `bundle_digest`, `yinyo.advanced_ref_attestation.v1`, `yinyo.frontier_readiness.v1`, `live_provenance.ws_sdk_session_id`, `ws_sdk_session_id`, `feishu_app_id_hash`, `sha256(app_id)`, `handoff_ready_records`, and a handoff that can pass `replay_handoff()`. Advanced scenarios must be captured through `record-advanced`. The bundle command inherits `ws_sdk_session_id` from config; if the operator passes the session id manually it must match, and the Feishu app hash must match `sha256(app_id)`.

```bash
python -m yinyo.cli config template --live-smoke > yinyo.env
python -m yinyo.cli smoke runbook --config ./yinyo.env
python -m yinyo.cli smoke preflight --config ./yinyo.env
python -m yinyo.cli smoke reset --config ./yinyo.env --confirm-reset
python -m yinyo.cli serve --config ./yinyo.env
python -m yinyo.cli smoke record-advanced --config ./yinyo.env --scenario image_understanding --image-ref <redacted-image-ref>
python -m yinyo.cli smoke wait --config ./yinyo.env
python -m yinyo.cli smoke bundle --config ./yinyo.env --output ./workspace/smoke-bundle --handoff-dir ./workspace/runs --live-attestation-id <attestation-id> --tenant-hash <sha256-tenant>
python scripts/verify_release.py --bundle ./workspace/smoke-bundle
python scripts/verify_release.py --target 1.0.0 --bundle ./workspace/smoke-bundle --candidate 1.0.0
python scripts/prepare_release_metadata.py --version 1.0.0 --verified-bundle ./workspace/smoke-bundle
python scripts/prepare_release_metadata.py --version 1.0.0 --verified-bundle ./workspace/smoke-bundle --apply
```

resource quotas are part of the local harness evidence and remain documented in the release matrix.

---

## Documents

| Document | Purpose |
|---|---|
| [docs/getting-started.zh-CN.md](docs/getting-started.zh-CN.md) | Chinese install and first-run guide. |
| [docs/feishu-user-acceptance.zh-CN.md](docs/feishu-user-acceptance.zh-CN.md) | Feishu user acceptance tasks. |
| [docs/external-testing.md](docs/external-testing.md) | External Feishu validation and redacted bundle handoff. |
| [docs/deployment.md](docs/deployment.md) | Deployment and runtime details. |
| [docs/benchmarking.md](docs/benchmarking.md) | Comparison method and limits. |
| [docs/release-evidence-matrix.md](docs/release-evidence-matrix.md) | Product and harness evidence matrix. |
| [docs/spec.md](docs/spec.md) | Product spec and acceptance gates. |
| [docs/production-checklist.md](docs/production-checklist.md) | Production and full-release checklist. |
| [RELEASE_NOTES.md](RELEASE_NOTES.md) | GitHub Release body and asset checklist. |
| [SECURITY.md](SECURITY.md) | Security boundaries. |

---

## License

MIT (c) 2026 Yinyo Contributors
