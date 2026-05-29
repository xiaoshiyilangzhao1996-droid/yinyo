<div align="center">

# YINYO

**一个面向飞书与 DeepSeek 的轻量 Harness Agent**

*飞书即入口 · DeepSeek 即大脑 · 记忆、证据与自进化内置*

![Status](https://img.shields.io/badge/status-lite-2ea043)
![Version](https://img.shields.io/badge/version-1.0.0--lite-2ea043)
![Package](https://img.shields.io/badge/python-1.0.0rc1-blue)
![Surface](https://img.shields.io/badge/surface-feishu-2ea043)
![Model](https://img.shields.io/badge/model-deepseek-f59e0b)
![Tests](https://img.shields.io/badge/tests-356%20local-2ea043)

**[中文](README.zh-CN.md) · [English](README.md) · [新手上手](docs/getting-started.zh-CN.md)**

</div>

YINYO 把一个可验证、可记忆、可进化的 Agent 放进飞书工作流里。你在飞书里和机器人对话，它在本地或服务器上接收事件、调用 DeepSeek、维护记忆、记录执行证据，并把可复用经验沉淀成能力。

> 设计哲学：**不要做万能平台，先把飞书里的真实工作流做好。**

---

## 目录

- [项目简介](#项目简介)
- [核心特性](#核心特性)
- [产品宪法](#产品宪法)
- [场景展示](#场景展示)
- [快速开始](#快速开始)
- [使用方式](#使用方式)
- [架构设计](#架构设计)
- [自进化机制](#自进化机制)
- [与同类产品对比](#与同类产品对比)
- [评测与证据](#评测与证据)
- [路线图](#路线图)
- [社区与反馈](#社区与反馈)
- [发布状态](#发布状态)
- [许可证](#许可证)

---

## 项目简介

YINYO 是一个围绕飞书与 DeepSeek 打磨的轻量 Harness Agent。它的出发点不是“什么平台都接一点”，而是先把一个真实办公入口做深：飞书负责触达用户，DeepSeek 负责推理生成，YINYO 负责把记忆、工具、证据和自进化组织成可运行、可验证、可交付的 Agent。

YINYO 的产品判断由三个核心驱动：

| 产品核心 | 含义 |
|---|---|
| **Less is more** | 先把飞书 + DeepSeek 这条主路径做窄、做稳、做清楚；少接入口，少堆概念，减少用户和 Agent 的操作负担。 |
| **Borrow what works** | 借鉴 Hermes、OpenClaw、HarnessAgent 研究和工程实践中有效的部分，但只留下能变成产品行为和测试证据的机制。 |
| **DeepSeek adapted** | 默认围绕 DeepSeek 的上下文、成本、重试、fallback、usage telemetry 和中文办公场景优化，而不是把模型当成可随意替换的黑盒。 |

YINYO 的行为风格由六个特质约束：好奇心、靠谱、事实洁癖、多元化思维、能忍受不确定性、低 ego 高自驱。它应该主动追问缺口，稳定执行任务，区分事实和猜测，从工具、记忆、产品、工程多个角度解决问题，在证据不足时承认不确定，并持续把失败沉淀成下一次可复用的能力。

YINYO 适合这些人：

- 想把 Agent 接进飞书群聊或私聊的个人用户。
- 想测试飞书办公流自动化的产品和研发团队。
- 想研究 harness Agent、记忆演化、Trace2Skill、自验证发布门禁的开发者。
- 想让另一个 Agent 按文档自动部署 YINYO 的高级用户。

---

## 核心特性

| 特性 | 说明 |
|---|---|
| **少而稳的入口** | 对应 Less is more：默认飞书长连接 `ws`，支持文本、图片、回复、卡片降级和重复事件保护。 |
| **能借鉴但不照搬** | 对应 Borrow what works：把记忆演化、Trace2Skill、release gate 等 harness 思路落到可运行代码和可回放证据。 |
| **DeepSeek 优先适配** | 对应 DeepSeek adapted：内置超时、重试、fallback、usage telemetry 和成本估算，面向中文办公对话优化。 |
| **靠谱执行** | 通过 runtime log、job、event store、outbox 和 single-writer runtime lock 记录每一步，减少“看起来回复了但实际没交付”。 |
| **事实洁癖** | TemporalTree 记忆通过 supersession 演化，区分新旧事实；证据不足时要求澄清，而不是编造上下文。 |
| **低 ego 高自驱** | Trace2Skill 会把重复失败提炼成技能，只有通过回放验证后才 promotion，让系统从失败中变得更可靠。 |

---

## 产品宪法

YINYO 保持三个产品核心：Less is more、Borrow what works、DeepSeek adapted。

YINYO 也保持六个行为特质：好奇心、靠谱、事实洁癖、多元化思维、能忍受不确定性、低 ego 高自驱。这些不是口号，而是映射到 [docs/release-evidence-matrix.md](docs/release-evidence-matrix.md) 的证据要求。

---

## 场景展示

| 场景 | 你说什么 | YINYO 做什么 |
|---|---|---|
| 工作整理 | “帮我把这段会议讨论整理成结论和行动项。” | 输出结构化结论、风险和下一步。 |
| 模糊澄清 | “帮我处理昨天那个问题。” | 承认信息不足，追问必要上下文。 |
| 图片理解 | 发送截图并问“这张图说明什么？” | 尝试识图；未配置视觉时给出清楚 fallback。 |
| 长对话推进 | 连续补充目标、限制、反馈 | 保留关键上下文并更新方案。 |
| 失败边界 | “读取你没有权限的私人聊天。” | 拒绝越权并给出可行替代方案。 |
| 发布验收 | 真实飞书使用后整理反馈 | 帮助维护者判断是否具备 full `1.0.0` 发布证据。 |

真实产品功能验收请看 [docs/feishu-user-acceptance.zh-CN.md](docs/feishu-user-acceptance.zh-CN.md)。

---

## 快速开始

> 推荐 Python 3.11、3.12 或 3.13。

### 给新手

按中文教程一步步安装、配置 DeepSeek、接入飞书：

[docs/getting-started.zh-CN.md](docs/getting-started.zh-CN.md)

### 给开发者

```bash
git clone https://github.com/xiaoshiyilangzhao1996-droid/yinyo.git
cd yinyo
python -m venv .venv
```

Windows PowerShell：

```powershell
.\.venv\Scripts\activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
python -m yinyo.cli config template > yinyo.env
```

Linux / macOS：

```bash
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
python -m yinyo.cli config template > yinyo.env
```

在 `yinyo.env` 里填写 `transport=ws`、飞书 App ID、飞书 App Secret 和 DeepSeek API Key。原始密钥只保留在本地。

启动前检查：

```bash
yinyo serve --config ./yinyo.env --dry-run
```

启动服务：

```bash
yinyo serve --config <path-to-yinyo.env>
```

---

## 使用方式

### 飞书机器人

YINYO 的默认产品入口是飞书机器人：

1. 在飞书开放平台创建企业自建应用。
2. 添加机器人能力。
3. 启用事件订阅和长连接。
4. 订阅 P2 IM 消息接收事件。
5. 配置消息发送/回复权限。
6. 在 `yinyo.env` 填入 `app_id`、`app_secret`、`deepseek_api_key`。
7. 启动 `yinyo serve --config <path-to-yinyo.env>`。

详细教程见 [docs/getting-started.zh-CN.md](docs/getting-started.zh-CN.md)。

### 命令行工具

| 命令 | 用途 |
|---|---|
| `yinyo config template` | 生成本地配置模板。 |
| `yinyo serve --config <config>` | 启动飞书 Agent 服务。 |
| `yinyo diagnose --config ./yinyo.env` | 查看运行状态和常见故障。 |
| `yinyo smoke status --config ./yinyo.env` | 查看发布证据链缺口。 |
| `python scripts/replay_scenarios.py --matrix` | 回放本地 harness 场景矩阵。 |

---

## 架构设计

YINYO 通过 **飞书事件入口 × DeepSeek 模型网关 × 记忆演化 × 证据链 × 发布门禁** 完成真实工作流。

### 1. Runtime Gateway

飞书事件先进入 runtime gateway。YINYO 会做事件标准化、幂等保护、ACK 边界、异步 job、outbox delivery 和 runtime log 记录，避免重复事件或慢模型调用阻塞飞书回调。

### 2. DeepSeek-first Model Gateway

模型调用不是裸调 API。YINYO 会记录 token usage、调用次数、重试、fallback 和估算成本，让后续诊断和发布证据能回看。

### 3. TemporalTree Memory

记忆不是简单追加文本。新事实可以 supersede 旧事实，搜索默认排除过期事实，并保留 audit trail。

### 4. Trace2Skill Evolution

重复失败不是只写日志。YINYO 会把失败路径提炼成 skill，生成 regression fixture，回放通过后才标记为可用能力。

### 5. Evidence & Release Gate

YINYO 的核心主张必须有证据：本地测试、scenario replay、runtime evidence、smoke bundle、release verifier。full `1.0.0` 必须有真实飞书 live evidence。

---

## 自进化机制

```text
[真实任务]
   |
   v
[运行与失败记录] -> runtime log / evidence / trace
   |
   v
[提炼可复用模式] -> Trace2Skill
   |
   v
[回放验证] -> regression fixture
   |
   v
[能力沉淀] -> 后续同类任务可复用
```

YINYO 的自进化不是“写一段总结就算学会”。它要求失败记录、技能提炼、回放验证和 promotion 状态都可追踪。

---

## 与同类产品对比

| 维度 | YINYO | GenericAgent | Hermes / OpenClaw |
|---|---|---|---|
| 第一入口 | 飞书机器人 | 本地电脑、浏览器、桌面/IM 多入口 | 更通用的 agent / harness 方向 |
| 设计取向 | 飞书 + DeepSeek 聚焦产品 | 极简自进化工具箱 | 更完整或更大规模的框架生态 |
| 记忆机制 | TemporalTree supersession | 分层 memory / SOP | 依实现而定 |
| 自进化 | Trace2Skill + regression replay | 任务经验 crystallize 为 skill | 多样化 |
| 发布方式 | release gate + live evidence | README 展示和技术报告驱动 | 项目各自定义 |
| 当前成熟度 | `1.0.0-lite`，等待真实飞书 live evidence | 已有丰富 demo 与社区资产 | 作为对标参考 |

YINYO 不声称比这些项目更成熟。它的差异是：把飞书办公场景、DeepSeek 模型假设、证据链和发布门禁收束成一个可下载、可验证的产品线。

---

## 评测与证据

当前公开可复验结果：

- `356` 个本地测试。
- `scripts/replay_scenarios.py --matrix` 覆盖 3 个产品核心、6 个行为特质和 ETCLOVG harness layer。
- `scripts/verify_release.py --target 1.0.0-lite --candidate 1.0.0-lite` 作为 lite 发布门禁。
- `scripts/verify_public_tree.py` 保证公开仓库不包含本地 runtime、build、secret、workspace 或缓存文件。

可运行：

```bash
python scripts/replay_scenarios.py --matrix
python scripts/verify_release.py --target 1.0.0-lite --candidate 1.0.0-lite
python scripts/verify_secrets.py
python scripts/verify_public_tree.py
python -m pytest tests -q
```

完整证据索引见 [docs/release-evidence-matrix.md](docs/release-evidence-matrix.md)。

---

## 路线图

| 阶段 | 目标 |
|---|---|
| `v1.0.0-lite` | 公开 GitHub 仓库、可下载、可配置 DeepSeek、可接入飞书、本地门禁可复验。 |
| 真实飞书验证 | 收集文本、图片、卡片降级、重复事件、长对话、失败处理等真实反馈。 |
| verified ws bundle | 维护者整理脱敏 live evidence bundle。 |
| full `v1.0.0` | verified live evidence 和 candidate guard 通过后发布稳定版。 |

更多见 [docs/roadmap.md](docs/roadmap.md) 和 [docs/versioning.md](docs/versioning.md)。

---

## 社区与反馈

当前官方入口：

- GitHub 仓库：[xiaoshiyilangzhao1996-droid/yinyo](https://github.com/xiaoshiyilangzhao1996-droid/yinyo)
- 问题反馈：[GitHub Issues](https://github.com/xiaoshiyilangzhao1996-droid/yinyo/issues)
- 新手教程：[docs/getting-started.zh-CN.md](docs/getting-started.zh-CN.md)
- 功能验收：[docs/feishu-user-acceptance.zh-CN.md](docs/feishu-user-acceptance.zh-CN.md)

反馈时请提供操作系统、Python 版本、YINYO commit、飞书 transport、脱敏错误信息和你想完成的真实工作流。不要提交 API Key、App Secret、原始 `yinyo.env`、私聊内容或 `workspace/` 原始 runtime 文件。

---

## 发布状态

当前外部版本：`1.0.0-lite`

Python 包版本：`1.0.0rc1`

当前版本：

| Surface | Value |
|---|---|
| Product version | `1.0.0-lite` |
| Python package | `1.0.0rc1` |
| Stable `1.0.0` | blocked until verified Feishu live evidence |

`v1.0.0-lite` 是面向下载和真实飞书验证的公开 lite 线，不是 full stable `v1.0.0`。这一点是产品边界，不是营销措辞。

full `1.0.0` 仍被真实飞书 live smoke 证据阻塞。完整候选发布要求 smoke 记录必须由 runtime logs、durable job records、event idempotency records 和 single-writer runtime lock 背书；主发布路径要求 `transport=ws`，并在 redacted runtime log 中包含 `service_start`、`ws_transport_start`、同一 event key 的 `ws_event_received` 和 ACK metrics。

维护者需要按 [docs/external-testing.md](docs/external-testing.md)、[docs/deployment.md](docs/deployment.md)、[docs/production-checklist.md](docs/production-checklist.md) 和 [RELEASE_NOTES.md](RELEASE_NOTES.md) 收集证据。bundle 必须包含 `bundle_digest`、`yinyo.advanced_ref_attestation.v1`、`yinyo.frontier_readiness.v1`、`live_provenance.ws_sdk_session_id`、`ws_sdk_session_id`、`feishu_app_id_hash`、`sha256(app_id)`、`handoff_ready_records`，并且 handoff 可以通过 `replay_handoff()`。Advanced live records 必须通过 `record-advanced` 捕获。`yinyo smoke bundle` 会 inherits `ws_sdk_session_id`；如果显式传入，must match config 里的值，飞书 app hash 也 must match `sha256(app_id)`。

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

resource quotas 是本地 harness evidence 的一部分，公开索引保留在 release matrix 中。

---

## 文档

| 文档 | 用途 |
|---|---|
| [docs/getting-started.zh-CN.md](docs/getting-started.zh-CN.md) | 中文新手入口：安装、DeepSeek、飞书接入、启动运行。 |
| [docs/feishu-user-acceptance.zh-CN.md](docs/feishu-user-acceptance.zh-CN.md) | 用户视角的飞书功能验收。 |
| [docs/external-testing.md](docs/external-testing.md) | 外部飞书验证和脱敏 bundle 交接。 |
| [docs/deployment.md](docs/deployment.md) | 服务部署和运行细节。 |
| [docs/benchmarking.md](docs/benchmarking.md) | 与 Hermes、OpenClaw 等项目的对标方法。 |
| [docs/release-evidence-matrix.md](docs/release-evidence-matrix.md) | 3+6 和 ETCLOVG 证据矩阵。 |
| [docs/spec.md](docs/spec.md) | 产品规格和验收门禁。 |
| [docs/production-checklist.md](docs/production-checklist.md) | 生产部署和 full release 清单。 |
| [RELEASE_NOTES.md](RELEASE_NOTES.md) | GitHub Release 正文和资产清单。 |
| [SECURITY.md](SECURITY.md) | 安全边界。 |

---

## 许可证

MIT (c) 2026 Yinyo Contributors
