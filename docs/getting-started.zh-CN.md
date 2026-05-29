<div align="center">

# YINYO 新手上手

"从下载到接入飞书，让小白用户和 Agent 都能跑起来。"

![Status](https://img.shields.io/badge/status-lite-2ea043)
![Install](https://img.shields.io/badge/install-python%203.11%2B-blue)
![Surface](https://img.shields.io/badge/surface-feishu--deepseek-2ea043)
![Release](https://img.shields.io/badge/version-1.0.0--lite-f59e0b)

</div>

这份文档是 YINYO 的中文新手入口。`README.zh-CN.md` 负责快速说明项目是什么、边界在哪里；本页负责把第一次下载安装、DeepSeek API Key、飞书自建应用、启动服务和后续学习路径讲清楚。

[看效果](#看效果) · [准备什么](#准备什么) · [安装](#安装) · [配置 DeepSeek](#配置-deepseek) · [接入飞书](#接入飞书) · [启动运行](#启动运行) · [Agent 安装法](#agent-安装法) · [社区与反馈](#社区与反馈) · [评测与路线图](#评测与路线图)

---

## 看效果

YINYO 的第一产品形态是一个跑在你自己机器或服务器上的飞书 Agent 服务。你在飞书里给机器人发消息，YINYO 接收飞书事件，调用 DeepSeek，使用自己的 memory、runtime gateway、evidence 和 release gate 机制完成回复。

| 你在飞书里做什么 | YINYO 负责什么 |
|---|---|
| 发普通文本 | 理解请求、调用模型、回复消息。 |
| 发图片 | 尝试解析图片；如果视觉能力没配置，会给出可继续的 fallback。 |
| 连续对话 | 保留必要上下文，避免每轮都从零开始。 |
| 触发失败场景 | 返回明确失败原因，并把 runtime 证据写入本地。 |
| 真实使用后反馈 | 帮助维护者判断 `1.0.0` 是否满足真实飞书可用性。 |

当前公开版本是 `v1.0.0-lite`。它适合下载、部署、接入飞书、开始真实验证；它还不是 full stable `v1.0.0`，因为 stable 需要真实飞书 live evidence。

---

## 准备什么

你需要：

- 一台能运行 Python 的电脑或服务器。
- Python 3.11、3.12 或 3.13。
- 一个 DeepSeek API Key。
- 一个飞书企业或测试企业。
- 一个飞书自建应用，并启用机器人能力。
- 能访问 GitHub 的网络环境。

推荐部署方式：

| 使用者 | 推荐 |
|---|---|
| 小白用户 | 先用 Windows 或 Linux 服务器，按本文一步步来。 |
| 有经验开发者 | clone 仓库后用虚拟环境安装。 |
| 让 Agent 帮你装 | 把本文链接交给 Codex、Claude Code、OpenClaw 或 GenericAgent，让它按步骤执行。 |

不要把 API Key、飞书 App Secret、`yinyo.env` 原文贴到聊天、GitHub issue 或截图里。

---

## 安装

### 方式一：从 GitHub 安装

适合希望看到源码、docs、examples 和 tests 的用户。

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
```

Linux / macOS：

```bash
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

### 方式二：从包安装

适合只想使用命令行，不关心源码的用户。

```bash
python -m pip install yinyo-agent==1.0.0rc1
```

包版本是 `1.0.0rc1`，对应产品版本 `1.0.0-lite`。这是 Python 包版本规则导致的命名差异，详见 [docs/versioning.md](versioning.md)。

### 检查命令是否可用

```bash
yinyo --help
```

如果系统找不到 `yinyo`，用 Python 模块方式运行：

```bash
python -m yinyo.cli --help
```

---

## 配置 DeepSeek

YINYO 默认按 DeepSeek-first 设计。你需要从 DeepSeek 控制台创建 API Key，然后写入本地配置文件。

在项目目录生成配置：

```bash
python -m yinyo.cli config template > yinyo.env
```

打开 `yinyo.env`，填写：

```env
deepseek_api_key=<your-deepseek-api-key>
deepseek_base_url=https://api.deepseek.com
default_model=deepseek-v4-flash
```

说明：

- `deepseek_api_key` 是必填。
- `deepseek_base_url` 默认是 DeepSeek 官方 API 地址。
- `default_model` 默认是 `deepseek-v4-flash`。
- 如果你使用企业代理或兼容网关，只改 `deepseek_base_url` 和 `default_model`，不要把代理密钥写进文档或 issue。

本地检查：

```bash
python -m yinyo.cli serve --config ./yinyo.env --dry-run
```

`dry-run` 只检查配置并打印脱敏信息，不会启动飞书服务。

---

## 接入飞书

YINYO 推荐使用飞书长连接 `ws`。这比 HTTP webhook 更适合小白用户，因为不需要公网回调地址。

### 1. 创建飞书自建应用

在飞书开放平台创建企业自建应用：

1. 登录飞书开放平台。
2. 创建企业自建应用。
3. 添加机器人能力。
4. 记录 `App ID` 和 `App Secret`。

如果你没有企业管理员权限，可以创建测试企业，或请管理员帮你审批应用。

### 2. 开启事件订阅

在应用后台配置：

- 启用事件订阅。
- 启用长连接模式。
- 订阅 P2 IM 消息接收事件。

YINYO 当前长连接入口会处理飞书消息事件，并把文本和图片消息送入同一个 runtime gateway。

### 3. 开通权限

至少需要与这些能力相匹配的权限：

- 接收用户发给机器人的消息。
- 以机器人身份发送或回复消息。
- 读取图片消息所需的资源权限，图片能力失败时会降级为文本 fallback。

飞书后台权限名称可能会随平台展示调整。实际开通时，以飞书开放平台提示为准；如果发送消息、回复消息或图片下载失败，先回到权限管理里补齐对应权限并重新发布应用版本。

### 4. 发布或审批应用

企业自建应用通常需要发布版本并通过管理员审批。测试企业可以由你自己审批。

### 5. 填写 YINYO 配置

编辑 `yinyo.env`：

```env
workspace=./workspace
profile=local
transport=ws
app_id=cli_xxx
app_secret=你的飞书 App Secret
deepseek_api_key=<your-deepseek-api-key>
```

长连接模式下，`verify_token` 可以留空。HTTP webhook 模式才需要 `verify_token` 和公网回调地址。

---

## 启动运行

先做本地检查：

```bash
python -m yinyo.cli serve --config ./yinyo.env --dry-run
```

通过后启动服务：

```bash
python -m yinyo.cli serve --config ./yinyo.env
```

保持这个终端打开。然后在飞书里找到你的机器人，发一条消息：

```text
你好，帮我把今天要做的事情整理成清单。
```

如果服务正常，你会看到机器人回复。运行过程中，YINYO 会把 runtime 状态写到 `workspace/` 下的本地 JSONL 文件里，这些文件不要提交到 GitHub。

常用检查命令：

```bash
python -m yinyo.cli diagnose --config ./yinyo.env
python -m yinyo.cli smoke status --config ./yinyo.env
```

`diagnose` 看运行状态；`smoke status` 看发布证据链缺什么。普通用户不需要理解每一项，维护者排障时会用到。

---

## Agent 安装法

如果你想让另一个 Agent 帮你安装 YINYO，把这段交给它：

```text
请按 https://github.com/xiaoshiyilangzhao1996-droid/yinyo/blob/main/docs/getting-started.zh-CN.md 安装并启动 YINYO。
要求：
1. 不要把 DeepSeek API Key、飞书 App Secret、yinyo.env 原文输出到聊天里。
2. 使用 Python 3.11/3.12/3.13 创建虚拟环境。
3. 生成 yinyo.env 后让我在本地填写密钥。
4. 先运行 dry-run，再启动 long-connection 服务。
5. 不提交 workspace、dist、build、release-artifacts 或任何 runtime JSONL。
```

Agent 应该帮你完成安装、环境检查和启动命令准备；密钥仍然由你自己在本地填。

---

## 常见问题

### 找不到 `yinyo` 命令

用模块方式运行：

```bash
python -m yinyo.cli serve --config ./yinyo.env
```

### 飞书没有回复

先确认：

- `yinyo serve` 终端还在运行。
- `transport=ws`。
- `app_id` 和 `app_secret` 正确。
- 飞书应用已经发布或审批。
- 事件订阅启用了长连接。
- 已订阅 P2 IM 消息接收事件。
- 消息发送权限已经开通。

再运行：

```bash
python -m yinyo.cli diagnose --config ./yinyo.env
```

### DeepSeek 调用失败

检查：

- `deepseek_api_key` 是否填入。
- Key 是否过期或余额不足。
- `deepseek_base_url` 是否能访问。
- 企业代理是否要求额外网络配置。

### 图片识别失败

这不一定代表服务不可用。YINYO 会尝试给出文本 fallback。请检查：

- 飞书图片资源权限。
- 服务器是否能访问飞书图片资源。
- 视觉模型或图片解析能力是否已配置。

### 误把密钥贴出来了

立刻去 DeepSeek 和飞书后台轮换密钥。不要只删除聊天记录或 issue。

---

## 社区与反馈

当前社区入口先以 GitHub 为主：

- 问题反馈：[GitHub Issues](https://github.com/xiaoshiyilangzhao1996-droid/yinyo/issues)
- 源码仓库：[GitHub Repository](https://github.com/xiaoshiyilangzhao1996-droid/yinyo)
- 中文上手：本页
- 产品功能验收：[docs/feishu-user-acceptance.zh-CN.md](feishu-user-acceptance.zh-CN.md)

反馈时请提供：

- 操作系统和 Python 版本。
- YINYO 版本或 commit。
- 你使用的是 `ws` 还是 `http`。
- 脱敏后的错误信息。
- 你期望它完成的真实飞书工作流。

不要提交：

- DeepSeek API Key。
- 飞书 App Secret。
- 原始 `yinyo.env`。
- 私聊、客户数据、会议原文或未脱敏截图。
- `workspace/` 下的原始 runtime 文件。

---

## 评测与路线图

YINYO 当前可公开说明的评测基础：

- `356` 个本地测试覆盖 agent loop、飞书网关、memory、evolution、model、governance 和 release gates。
- `scripts/replay_scenarios.py --matrix` 覆盖 3 个产品核心、6 个行为特质和 ETCLOVG harness layer。
- `scripts/verify_release.py --target 1.0.0-lite --candidate 1.0.0-lite` 是 lite 发布门禁。
- `scripts/verify_public_tree.py` 保证公开仓库不包含本地 runtime、build、secret、workspace 或缓存文件。

YINYO 不声称当前 `v1.0.0-lite` 已经等于 full stable `v1.0.0`。下一阶段路线图：

| 阶段 | 目标 |
|---|---|
| `v1.0.0-lite` | GitHub 下载、DeepSeek 配置、飞书接入、本地门禁可复验。 |
| 真实飞书验证 | 收集文本、图片、卡片降级、重复事件、长对话、失败处理等真实使用反馈。 |
| verified ws bundle | 维护者把真实使用证据整理为脱敏 bundle。 |
| full `v1.0.0` | 只有 verified live evidence 和 candidate guard 通过后才发布。 |

更多细节：

- [docs/benchmarking.md](benchmarking.md)
- [docs/release-evidence-matrix.md](release-evidence-matrix.md)
- [docs/roadmap.md](roadmap.md)
- [docs/versioning.md](versioning.md)

---

## 下一步

第一次跑通后，你可以继续看：

| 你想做什么 | 继续阅读 |
|---|---|
| 理解项目定位 | [README.zh-CN.md](../README.zh-CN.md) |
| 部署到服务器 | [docs/deployment.md](deployment.md) |
| 做产品功能验收 | [docs/feishu-user-acceptance.zh-CN.md](feishu-user-acceptance.zh-CN.md) |
| 收集 release evidence | [docs/external-testing.md](external-testing.md) |
| 看发布边界 | [docs/versioning.md](versioning.md) |
| 看安全边界 | [SECURITY.md](../SECURITY.md) |
