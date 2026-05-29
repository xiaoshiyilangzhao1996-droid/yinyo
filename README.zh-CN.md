<div align="center">

# YINYO

"面向飞书 + DeepSeek 工作流的 harness Agent：会记忆、会验证、会进化。"

![Status](https://img.shields.io/badge/status-lite-2ea043)
![Version](https://img.shields.io/badge/version-1.0.0--lite-2ea043)
![Scope](https://img.shields.io/badge/scope-harness--agent-blue)
![Tests](https://img.shields.io/badge/tests-356%20local-2ea043)
![Release](https://img.shields.io/badge/1.0-blocked%20by%20live%20smoke-d73a49)

</div>

YINYO 是一个按 Hermes 和 OpenClaw 这类 harness Agent 设计预期对标的聚焦型产品，不是通用聊天机器人包装层。它以飞书和 DeepSeek 作为第一产品落地面，把运行时网关、DeepSeek 优先模型网关、TemporalTree 记忆、Trace2Skill 进化、证据记录和发布门禁放进同一条可部署产品线。对标方法和边界见 [docs/benchmarking.md](docs/benchmarking.md)。

[快速开始](#快速开始) · [外部测试](#外部测试) · [产品宪法](#产品宪法) · [它做什么](#它做什么) · [运行方式](#运行方式) · [发布状态](#发布状态) · [边界](#边界) · [校验](#校验)

---

## 快速开始

```bash
pip install yinyo-agent
cp yinyo.env.example yinyo.env
yinyo serve --workspace ./workspace --profile local --transport ws
```

本地配置检查：

```bash
yinyo serve --workspace ./workspace --dry-run
```

---

## 外部测试

GitHub 用户可以用 `v1.0.0-lite` 连接真实飞书应用测试。[docs/external-testing.md](docs/external-testing.md) 从 clone 或安装开始，说明如何配置飞书自建应用、启动长连接服务、收集脱敏 smoke evidence，并在不泄露密钥的前提下共享 `smoke-bundle`。

外部 live 报告可以进入 `1.0.0` 评审，但只有严格候选门禁带 verified ws bundle 通过后，才能发布 `v1.0.0`：

```bash
python scripts/verify_release.py --target 1.0.0 --bundle <bundle-dir> --candidate 1.0.0
```

---

## 产品宪法

YINYO 保持三个产品核心：

| Core | Meaning |
|---|---|
| Less is more | 飞书优先、小而可审计的工具面，不做平台泛化。 |
| Borrow what works | 研究启发的 memory、context、evolution 机制必须产生可测试行为。 |
| DeepSeek adapted | 大上下文、低成本调用、tool calling、retry/fallback、usage telemetry 是一等设计假设。 |

YINYO 还保持六个行为特质：好奇心、靠谱、事实洁癖、多元化思维、能忍受不确定性、低 ego 高自驱。Release matrix 会把每个核心和特质映射到本地可执行证据；`1.0.0` 还要求真实飞书证据证明同一组 product claim。公开证据索引见 [docs/release-evidence-matrix.md](docs/release-evidence-matrix.md)。

---

## 它做什么

| Capability | Product path |
|---|---|
| Harness runtime | 飞书长连接 transport、HTTP fallback、event verification、idempotency、jobs、outbox、smoke evidence。 |
| DeepSeek-first execution | Provider chain、usage accounting、retry/fallback metadata、run manifest 成本估算。 |
| Durable memory | TemporalTree facts 通过 supersession 演化，避免 stale notes 堆积。 |
| Self-improvement | Trace2Skill 把重复失败提取成 skill，记录 regression fixture，并只在 replay evidence 后 promotion。 |
| Evidence hygiene | Tool calls、blocked actions、redacted smoke records、release checks 都会持久化。 |
| 3+6 evidence matrix | Scenario replay 把产品核心和行为特质映射到 executable checks。 |

---

## 运行方式

默认产品 transport 是飞书长连接 `ws`。HTTP webhook 保留为 fallback 和本地诊断路径。

---

## 发布状态

当前外部版本：`1.0.0-lite`

Python 包版本：`1.0.0rc1`

这是面向 GitHub 下载和真实飞书验证的公开 lite 线，不是 full stable `1.0.0`。历史 `v8.x` 只是内部原型里程碑，不再作为公开产品版本。

`1.0.0` 仍被真实飞书 live smoke 证据阻塞。至少需要：

| Smoke scenario | Required |
|---|---:|
| URL verification | HTTP only |
| Text message reply | yes |
| Image message reply | yes |
| Card fallback | yes |
| Duplicate callback | yes |

`1.0.0` 还需要 image understanding、long conversation、memory supersession、Trace2Skill promotion、DeepSeek usage telemetry 和 partial failure behavior 的飞书 live advanced 记录。本地 replay 不能替代 live 平台证据。

---

## 边界

YINYO 聚焦飞书和 DeepSeek-centered agent workflows，不追求成为通用 multi-platform agent gateway。

当前 release matrix 已经用本地可执行证据覆盖 image understanding、long-context retention、memory supersession、TemporalTree state recovery、Trace2Skill promotion、ACK boundary、worker saturation、runtime single-writer locking、workspace boundary enforcement、resource quotas、trace-native failure diagnosis、state handoff、model usage、adaptive simplification、card fallback、partial failure 和 release blocking。这些高价值本地场景已经绑定到 versioned harness corpus。公开 `1.0.0` 之前仍必须补齐真实飞书 live smoke。

`1.0.0` 门禁要求 smoke 记录必须由 matching runtime logs、durable job records、event idempotency records，以及本地 JSONL stores 使用的 single-writer runtime lock 背书。

---

## 校验

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

`1.0.0` 候选发布必须额外通过：

```bash
python -m yinyo.cli config template --live-smoke > yinyo.env
python -m yinyo.cli smoke runbook --config ./yinyo.env
python -m yinyo.cli smoke preflight --config ./yinyo.env
python -m yinyo.cli smoke reset --config ./yinyo.env --confirm-reset
python -m yinyo.cli serve --config ./yinyo.env
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

runbook 会带上当前 evidence snapshot、`operator_plan` 和 `yinyo.frontier_readiness.v1`，让实测操作者在收集证据前直接看到 basic、advanced、runtime、diagnostic、handoff、frontier-harness 哪些层还缺。

Release verifier 的 JSON 模式会输出机器可读的 R1 readiness audit，覆盖 `docs/spec.md` 的每一条 1.0 release criterion。Advanced live records 必须通过 `yinyo smoke record-advanced` 捕获；手写 advanced JSONL records 会被 1.0 证据校验拒绝。`--candidate 1.0.0` 是最终 tag/publish guard，要求 `--target 1.0.0` 加上 verified live smoke evidence 或 verified redacted bundle，才允许把 `v1.0.0` 视为可发布。

Candidate `1.0.0` 要求 `transport=ws` 长连接 bundle；HTTP evidence 只是 fallback 检查，不是主发布证明。ws bundle 还必须包含脱敏的至少一个 run-level `handoff.json`，并且它必须能通过 `replay_handoff()` 恢复成 `yinyo.handoff_resume.v1`，所以 manifest 里的 `handoff_ready_records > 0`；还必须包含 `smoke_mode=false` 的 `service_start`、`ws_transport_start`，并且每个 basic smoke 场景都要有同一 `event_key` 的 `ws_event_received` runtime log，其中要有 startup config fields、ACK metrics 和 Feishu deadline 内的 ACK 证据。主 ws 发布路径不要求 HTTP `url_verification` 证据。Bundle manifest 包含每个脱敏证据和 handoff 文件的 SHA-256 hash 和稳定 `bundle_digest`；校验会拒绝替换文件、不可 replay 的 handoff packet、digest drift、`yinyo.advanced_ref_attestation.v1` 漂移，或 ETCLOVG、TemporalTree、trace diagnosis、handoff、adaptive simplification 相关 frontier readiness 缺口。Candidate bundle 还必须包含 manifest `yinyo.live_provenance.v1`，记录脱敏 operator attestation id、飞书 app hash、tenant hash 和 ws SDK session id；verifier 会把 `live_provenance.ws_sdk_session_id` 与 redacted runtime log 里的 `service_start`、`ws_transport_start` 的 `ws_sdk_session_id` marker 交叉校验，防止本地 synthetic fixture 冒充真实飞书证据。

`yinyo smoke bundle` 会从 `yinyo.env` inherits `ws_sdk_session_id`；如果传入 `--ws-sdk-session-id`，它 must match config 里的值。它还会从 config 里的 `app_id` 计算 `feishu_app_id_hash = sha256(app_id)`；如果传入 `--feishu-app-id-hash`，它 must match `sha256(app_id)`。

live `card_fallback` smoke 场景需要临时在 `yinyo.env` 设置 `smoke_mode=true`，并向机器人发送 `/yinyo-smoke card-fallback`；之后关闭 smoke mode、重启，再收集其他 live 场景并构建最终 bundle。

---

## 文档

| 文档 | 用途 |
|---|---|
| [docs/external-testing.md](docs/external-testing.md) | GitHub 测试者真实飞书验证和脱敏 bundle 共享指南。 |
| [README.md](README.md) | 英文 canonical 项目主页。 |
| [docs/release-evidence-matrix.md](docs/release-evidence-matrix.md) | 公开 3+6 和 ETCLOVG 证据索引。 |
| [docs/benchmarking.md](docs/benchmarking.md) | Hermes/OpenClaw 对标方法和边界。 |
| [docs/handoff.md](docs/handoff.md) | 跨会话产品背景和当前证据边界。 |
| [docs/spec.md](docs/spec.md) | 产品规格和验收门禁。 |
| [docs/roadmap.md](docs/roadmap.md) | alpha 到 `1.0.0` 的缺口。 |
| [docs/deployment.md](docs/deployment.md) | 服务部署和 smoke 工作流。 |
| [docs/production-checklist.md](docs/production-checklist.md) | 发布准备清单。 |
| [docs/versioning.md](docs/versioning.md) | 外部 SemVer 和内部 gate 策略。 |
| [RELEASE_NOTES.md](RELEASE_NOTES.md) | `v1.0.0-lite` 的 GitHub Release 正文和资产清单。 |
| [MAINTENANCE.md](MAINTENANCE.md) | 维护和验证命令。 |
| [SECURITY.md](SECURITY.md) | 安全和数据边界策略。 |
| [AGENTS.md](AGENTS.md) | 后续 Agent 的协作规则。 |

---

## 许可证

MIT (c) 2026 Yinyo Contributors
