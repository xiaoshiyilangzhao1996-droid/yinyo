YINYO — 独立飞书 Agent 产品 Spec v5.0
**纲领：** Less is more。纯 ReAct + 轻量 Plan。顶级飞书体验。以证据为锚。DeepSeek 高适配。
**定位：** 一个独立的飞书 Agent 产品。DeepSeek-first。~2,000 行。
**融合来源：** GA 架构 + OpenClaw Lark 格式引擎 + Hermes Card 2.0 + Plan-and-Solve (Wang 2023)
**版本：** v5.0 | **日期：** 2026-05-24
**核心新增：** 飞书适配层（12 项全绿）+ 会话管理 + SOUL 定义 + 命令系统

目录
[1. 终局判词](#1-终局判词)
[2. 设计原则与边界](#2-设计原则与边界)
[3. 架构总览](#3-架构总览)
[4. 组件规范](#4-组件规范)
[5. 飞书适配层 Spec](#5-飞书适配层-spec)
[6. SOUL 定义](#6-soul-定义)
[7. ADR](#7-adr)
[8. Phase Plan](#8-phase-plan)

---

## 1. 终局判词

**YINYO 是一个独立的飞书 Agent 产品。** 不是被调用的 runtime，不是 Hermes 的子 Agent。它有自己的飞书 bot、自己的 SOUL、自己的会话管理。用户在飞书里直接跟 YINYO 对话，像跟 Hermes 对话一样。

### 1.1 核心差异化

| 能力 | GA | Codex | Claude | Hermes | **YINYO v5.0** |
|------|:--:|:-----:|:------:|:------:|:--------------:|
| Agent 模式 | ReAct | ReAct | ReAct | ReAct | **ReAct + Plan** |
| 并行工具调用 | ❌ | ❌ | ✅ | ✅ | ✅ DeepSeek 原生 |
| Evidence Ledger | ❌ | ❌ | ❌ | ❌ | ✅ JSONL |
| Verification Gate | ❌ | ❌ | ❌ | ❌ | ✅ 三态 |
| 技能自结晶 | ✅ | ❌ | ❌ | ❌ | ✅ 3次→Skill |
| 语义记忆检索 | ❌ | ❌ | ❌ | ❌ | ✅ TF-IDF |
| 通讯接入 | 7 平台 | ❌ | ❌ | 20+ 平台 | **飞书（顶级）** |
| 消息格式 | post | N/A | N/A | Card 2.0 | **Card 2.0 全特性** |
| 会话管理 | ✅ | ❌ | ❌ | ✅ | ✅ /new /continue |
| 主动反馈 | ❌ | ❌ | ❌ | ✅ reactions | ✅ reactions |

---

## 2. 设计原则与边界

### 2.1 核心原则（不变 + 新增第 7 条）

| # | 原则 | 含义 |
|---|------|------|
| 1 | 能力进化，而非预设 | 通过工具 + 记忆 → 技能结晶 |
| 2 | 信息密度最大化 | 每行代码承载一个概念 |
| 3 | 证据即真相 | 每个 action 有 evidence ref |
| 4 | 纯 ReAct + Plan | Plan-and-Solve → ReAct Execute |
| 5 | 自述能力 = 核心功能 | 能读内存、分析技能、报告状态 |
| 6 | 三层记忆隔离 | L1≠L2≠L3，职责不混用 |
| **7** | **飞书体验第一** | 飞书是唯一用户触点。消息格式、防截断、状态反馈必须达到所有 Agent 的最顶级 |

### 2.2 不做的事（v5.0 新增）

| ❌ 不做 | 原因 |
|---------|------|
| 多平台通讯 | Less is more。飞书一个够了 |
| 桌面/GUI/Web | 飞书就是 UI |
| 多模型 gateway | DeepSeek-first |
| ACP 桥接 | 未来考虑 |

---

## 3. 架构总览

```
┌──────────────────────────────────────────────────────────────┐
│              YINYO v5.0 — 独立飞书 Agent (~2,000 行)          │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  飞书适配层    [~400 行]  ★ v5.0 新增                  │    │
│  │    · Webhook 接收 / 消息路由 / 去重                     │    │
│  │    · Card 2.0 消息构建（标题降级/表格转换/代码块保护）  │    │
│  │    · 长消息智能分段（段落边界感知）                      │    │
│  │    · Processing 状态反应 + 文件/媒体发送                 │    │
│  │    · @提及标准化                                        │    │
│  │    · Card 拒绝 → 纯文本 fallback                        │    │
│  └──────────────────────┬───────────────────────────────┘    │
│                         │                                     │
│  ┌──────────────────────┴───────────────────────────────┐    │
│  │  Session Manager [~100 行]  ★ v5.0 新增                │    │
│  │    · 多用户/多对话 session 隔离                         │    │
│  │    · /new /stop /continue /help 命令                   │    │
│  │    · Session TTL + 自动清理                            │    │
│  │    · 消息去重（TTL-based dedup）                       │    │
│  └──────────────────────┬───────────────────────────────┘    │
│                         │                                     │
│  Agent Loop [~290 行]    Context [~130 行]    Model [~160 行] │
│  Evidence  [~140 行]     Memory  [~220 行]    Tools [~450 行] │
│  Governance[~95 行]      Evolution[~140 行]                    │
└──────────────────────────────────────────────────────────────┘
```

### 3.1 行数预算（v5.0）

```
yinyo/
├── __init__.py              ←  20 行
├── agent.py                 ← 300 行  (ReAct + Plan + handle_message)
├── session.py               ← 120 行  ★ 会话管理 + 命令系统
├── feishu_adapter.py        ← 200 行  ★ webhook + 消息路由
├── feishu_card.py           ← 150 行  ★ Card 2.0 构建 + 格式优化
├── feishu_format.py         ← 200 行  ★ 标题降级/表格转换/代码块保护/分段
├── context.py               ← 130 行
├── evidence.py              ← 140 行
├── memory.py                ← 220 行
├── model.py                 ← 160 行
├── governance.py            ←  95 行
├── tools.py                 ← 450 行
├── evolution.py             ← 140 行
├── SOUL.md                  ←  50 行  ★ YINYO 身份定义
─────────────                ────
总计                         ~2,400 行
新增 ~800 行：飞书适配 (550) + 会话管理 (120) + SOUL (50) + agent 更新 (80)
```

---

## 4. 组件规范（新增/修改部分）

### 4.1 Agent Loop（v5.0 更新：消息驱动入口）

```python
class YinyoAgent:
    def handle_message(self, user_id: str, chat_id: str, text: str) -> dict:
        """消息驱动入口。处理飞书消息，返回回复内容。"""
        session = self.session_manager.get_or_create(user_id, chat_id)
        
        # 命令拦截
        if text.startswith('/'):
            return self.session_manager.handle_command(text, session)
        
        # 消息去重
        if self.session_manager.is_duplicate(text, user_id):
            return None  # 不回复
        
        # 注入消息到 session
        session.add_user_message(text)
        
        # 执行 Agent Loop
        result = self.run(text)  # 内部 run() 不变
        
        # 记录到 session
        session.add_assistant_message(result)
        
        return {
            "text": result.get("final_response", ""),
            "files": result.get("files", []),
            "reaction": "processing"  # 先发 processing 反应
        }
```

### 4.2 Session Manager（★ v5.0 新增）

```python
class SessionManager:
    """多用户/多对话 session 管理。"""
    
    def __init__(self, workspace: str, ttl: int = 3600):
        self.sessions: dict[str, Session] = {}
        self.ttl = ttl
        self.dedup_store: dict[str, float] = {}  # msg_hash → timestamp
    
    def get_or_create(self, user_id: str, chat_id: str) -> Session:
        sid = f"{user_id}:{chat_id}"
        if sid not in self.sessions:
            self.sessions[sid] = Session(user_id, chat_id)
        return self.sessions[sid]
    
    def handle_command(self, text: str, session: Session) -> dict:
        cmd, *args = text.split()
        if cmd == '/new':
            session.clear()
            return {"text": "✅ 新对话已开始。"}
        elif cmd == '/stop':
            session.stop()
            return {"text": "⏹ 任务已停止。"}
        elif cmd == '/status':
            return {"text": session.status_report()}
        elif cmd == '/help':
            return {"text": COMMAND_HELP}
        return {"text": f"未知命令: {cmd}。输入 /help 查看可用命令。"}
    
    def is_duplicate(self, text: str, user_id: str) -> bool:
        """消息去重（TTL 60s）。"""
        import hashlib, time
        h = hashlib.md5(f"{user_id}:{text}".encode()).hexdigest()
        now = time.time()
        if h in self.dedup_store and now - self.dedup_store[h] < 60:
            return True
        self.dedup_store[h] = now
        return False
```

---

## 5. 飞书适配层 Spec（★ v5.0 核心新增）

### 5.1 三层架构

```
飞书 Webhook（消息接收）
       │
       ▼
feishu_adapter.py   ← HTTP server + 消息路由
       │
       ├─→ feishu_card.py     ← Card 2.0 构建
       │      └─→ feishu_format.py  ← 格式优化引擎
       │
       └─→ YinyoAgent.handle_message()
```

### 5.2 飞书卡片格式引擎（对标 OpenClaw + Hermes）

**5.2.1 标题降级**（来自 OpenClaw markdown-style.ts）

飞书 Card 2.0 在消息卡片中不需要大标题。H1 → H4，H2-H6 → H5。

```
原文：  # 大标题          → #### 大标题
原文：  ## 二级标题        → ##### 二级标题
原文：  ### 三级标题       → ##### 三级标题
```

**5.2.2 Markdown 表格 → 飞书兼容格式**（来自 OpenClaw Lark + Hermes #9549）

飞书 md tag 不支持表格语法。自动转换：
- `convertMarkdownTables(mode='bullets')` → 每行变成 `• col1: val1, col2: val2`
- `convertMarkdownTables(mode='code')` → 表格内容放入 ``` 代码块

默认模式：检测列数，≤3 列用 bullets，>3 列用 code。

**5.2.3 代码块保护**（来自 OpenClaw + Hermes）

格式优化时用占位符保护代码块，处理完后还原。确保代码内容不被标题降级/表格转换误伤。

**5.2.4 Card 2.0 消息构建**（来自 Hermes feishu.py v2）

```python
def build_card_payload(markdown: str, title: str = "") -> str:
    """构建 Feishu Card 2.0 消息 payload。"""
    return json.dumps({
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": title or "YINYO"},
            "template": "blue" if not title else "wathet"
        },
        "elements": [
            {"tag": "markdown", "content": markdown}
        ]
    })
```

**5.2.5 长消息智能分段**（来自 Hermes adaptive batch）

飞书 Card 2.0 单条消息限制约 30KB。超长时自动分段：
- 优先在段落边界（`\n\n`）切割
- 保护代码块完整性（不在代码块中间切割）
- 分段之间添加 `(1/3) (2/3) (3/3)` 标记
- 300ms batch delay 防止飞书限流

**5.2.6 Card 拒绝 → 纯文本 fallback**（来自 Hermes）

```
尝试 Card 2.0 发送
  ├─ 成功 → done
  └─ API 返回 230099（"Failed to create card content"）
       └─ 自动降级：纯文本 + strip_markdown()
```

### 5.3 消息处理管线

```
接收消息
  ├─ 1. 消息去重（TTL 60s）
  ├─ 2. @提及解析 → 标准化
  ├─ 3. 文件/图片/音频附件提取
  ├─ 4. 分享卡片内容提取
  ├─ 5. 路由到 Agent.handle_message()
  ├─ 6. Processing 反应（飞书 reaction API）
  ├─ 7. Agent 处理...
  ├─ 8. 移除 Processing 反应
  └─ 9. 构建回复（feishu_card.py）
       ├─ a. 格式优化（feishu_format.py）
       ├─ b. Card 2.0 payload
       ├─ c. 长消息检测 → 分段发送
       └─ d. 文件/媒体附件注入
```

### 5.4 12 项顶级特性清单

| # | 特性 | 来源 | 说明 |
|---|------|------|------|
| 1 | Card 2.0 消息格式 | Hermes v2 | 替代旧 post 格式，支持更丰富的布局 |
| 2 | 标题降级 H→H4-H5 | OpenClaw | 卡片中不需要大标题，降级后更美观 |
| 3 | 表格→列表/代码转换 | OpenClaw + Hermes | 飞书不支持 md 表格，≤3 列用 bullets，>3 列用 code |
| 4 | 代码块保护 + 拆分 | OpenClaw + Hermes | 格式优化时保护代码块，长代码块智能分段 |
| 5 | 长消息段落边界分段 | Hermes | `\n\n` 边界切割 + `(1/3)` 标记 + 代码块完整性 |
| 6 | Card 拒绝→纯文本降级 | Hermes | API error 230099 时自动 fallback |
| 7 | Processing 状态反应 | Hermes | 开始处理时添加 👍↻ 反应，完成后移除 |
| 8 | 消息去重（TTL 60s）| GA | MD5 hash + timestamp，飞书重连去重 |
| 9 | 文件/图片/视频/音频发送 | GA | 自动识别附件类型，上传到飞书 |
| 10 | @提及标准化 | OpenClaw | 解析 `<at>` 标签，`@open_id` 格式标准化 |
| 11 | reply 保持上下文 | GA/Hermes | 回复消息时关联原始消息，保持飞书 UI 上下文 |
| 12 | 自适应 batch delay | Hermes | 分段发送时 300ms 延迟，防止飞书限流 |

---

## 6. SOUL 定义

```markdown
# YINYO — 隐曜

我是 yinyo 隐曜，一个独立的飞书 Agent 产品。我的设计哲学是 Less is more。

## 核心身份
- 独立产品，不依附于任何平台
- DeepSeek-first，追求极致 token 效率
- 以证据为锚，不自报"完成"而不验证
- 能力通过工具+记忆→技能结晶自然生长

## 行为准则
- 真实有用，不表演有用
- 先查再问，能自己做的不打扰用户
- 有判断，可以赞同也可以反驳
- 简洁直接，不废话

## 飞书交互
- 消息用 Markdown，关键信息用 **粗体**
- 代码用 ``` 代码块
- 长回复自动分段
- 处理中先给 reaction 👍
```

---

## 7. ADR（新增）

### ADR-0007：飞书是唯一通讯平台

**背景：** GA 支持 7 个通讯平台，Hermes 支持 20+。YINYO 作为独立 Agent 产品需要通讯接入。

**决策：** 只做飞书一个平台，但要做到所有 Agent 的飞书体验最顶级。

**理由：**
- Less is more：一个平台做到极致 > 多个平台平庸
- 对标 GA/Hermes/OpenClaw 的飞书适配，吸收三方最优特性
- 飞书是中国用户的主流工作 IM，覆盖面足够

### ADR-0008：Card 2.0 + 格式引擎是独立模块

**决策：** 飞书格式引擎（feishu_card.py + feishu_format.py）作为独立模块，不耦合 Agent Loop。

**理由：**
- 格式优化是纯文本处理，不涉及模型调用
- 可独立测试、独立迭代
- 未来即使换通讯平台，Agent Loop 零改动

---

## 8. Phase Plan（v5.0 更新）

### Phase 1 — Skeleton
### Phase 2 — DeepSeek Adapter
### Phase 3 — Tool Adapters
### Phase 4 — Loop Integration
### Phase 5 — Governance & Evolution Hardening
### Phase 6 — ★ Feishu Integration & Deploy（v5.0 新增）
- feishu_adapter.py — webhook server + 消息路由
- feishu_card.py — Card 2.0 构建
- feishu_format.py — 格式优化引擎（12 项特性全覆盖）
- session.py — 多用户会话管理 + 命令系统
- SOUL.md — YINYO 身份定义
- 端到端飞书消息收发测试
- Processing reaction + 文件/媒体发送

---

## 9. v4.0 → v5.0 变更清单

| 变更 | 来源 | 说明 |
|------|------|------|
| ★ 飞书适配层 | GA + OpenClaw + Hermes | ~550 行，12 项顶级特性全覆盖 |
| ★ 会话管理 | GA + Hermes | ~120 行，多用户隔离 + 命令系统 |
| ★ SOUL 定义 | GA | YINYO 独立身份 |
| ★ 消息驱动入口 | GA | agent.handle_message() 替代纯 run() |
| △ 定位更新 | 视角修正 | 从 runtime → 独立飞书 Agent 产品 |
| △ 竞品对比表 | 视角修正 | 增加"通讯接入"维度 |
| △ 行数预算 | 实际实现 | ~1,600 → ~2,400 行 |

**通过率演进：** v2.1: 48.9% → v3.0: 97.8% → v4.0: 100% → v5.0: 待审计
