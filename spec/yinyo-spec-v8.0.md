YINYO v7.0 → v8.0 变更 Spec
======================

## 变更概述

v8.0 补齐盲测发现的 5 个真实能力缺口。每一项都遵循「集百家之长 + 高适配 DeepSeek」原则。

**核心认知转变：DeepSeek V4 1M 上下文 + $0.27/M tokens → 不再抠 token，用 LLM 取代规则。**

| 缺口 | 方案 | 论文/实践支撑 |
|------|------|-------------|
| P1-5 Vision | vision_adapter（外部视觉模型 + 文本注入） | DeepSeek V4 无原生 Vision，用 adapter 模式 |
| P1-3 子 Agent | delegate_task（监督者-工人模式，共享完整上下文） | Cognition.ai「Don't Build Multi-Agents」原则 1+2；LangChain subagent pattern |
| P1-4+P0-2 记忆扩容 | Mem0 Multi-Scope 设计 + LLM 事实提取 + 10K chars MEMORY | Mem0 ECAI 2025：92.5 LoCoMo；Multi-Scope 标记 |
| P2-7 跨 Provider | provider_chain（DeepSeek Flash→Pro→GLM 自动降级） | OpenClaw provider registry 模式 |
| P2-8 SOP 闭环 | Trace2Skill：自动检测失败模式→提取技能→自动加载 | AHE self-evolution + Trace2Skill 论文 |

---

## 1. Vision Adapter（`vision_adapter.py`，新增 ~120 行）

### 设计原则
DeepSeek V4 Pro/Flash 不提供原生 Vision API。采用 **adapter 模式**：外部视觉模型识别 → 文本描述注入 DeepSeek 上下文。

### 架构
```
Feishu 图片消息
      │
      ▼
┌─────────────────────┐
│  vision_adapter.py  │
│  - 图片下载/解码     │
│  - 调用视觉模型      │
│  - 返回文本描述      │
└────────┬────────────┘
         │
         ▼  "[Vision: 这是一张报错截图，显示
              ModuleNotFoundError: No module named 'xxx']"
         │
         ▼
   DeepSeek V4 Agent（文本推理）
```

### 视觉模型选择
- **默认**: OpenAI GPT-4o-mini Vision（最便宜的多模态 API）
- **备选**: Qwen-VL-Max / GLM-4V（国内可用）
- **配置**: 通过 config 或环境变量 `VISION_PROVIDER` / `VISION_API_KEY`

### 新增工具：do_vision
```python
@tool(permission="ALLOW")
def do_vision(image_source: str, query: str = "描述这张图片") -> dict
```
- `image_source`: 本地路径、URL、或 base64
- `query`: 对图片的具体问题
- 返回: `{"description": "...", "model": "gpt-4o-mini", "tokens": 150}`

### Feishu 集成
- `feishu_adapter.py` 检测图片消息 → 自动调用 `do_vision` → 将描述文本注入对话上下文
- 用户无感：发图 → Agent 看到的是文字描述 + 原始图片引用

---

## 2. Sub-Agent 委托（`delegate.py`，新增 ~200 行）

### 设计原则
遵循 **Cognition.ai「Don't Build Multi-Agents」两原则**：
1. **共享完整上下文** — 子 Agent 看到父 Agent 的全部对话历史
2. **动作携带隐式决策** — 子 Agent 返回完整工具调用轨迹，不只是结果

### 架构：监督者-工人（Supervisor-Worker）
```
Main Agent（监督者）
  │
  │  decompose: 将复杂任务拆成独立子任务
  │
  ├─▶ Worker 1: 独立 ReAct 循环（共享上下文）
  ├─▶ Worker 2: 独立 ReAct 循环（共享上下文）  ← 并行执行
  └─▶ Worker 3: 独立 ReAct 循环（共享上下文）
  │
  │  merge: 汇总结果
  │
  ▼
Final Response
```

### 新增工具：delegate_task
```python
@tool(permission="ALLOW")
def delegate_task(goal: str, context: str = "") -> dict
```
- 子 Agent 获得独立 ReAct 循环（max 20 steps）
- 子 Agent 返回：`{result, tool_traces, steps, status}`
- 并行调用：主 Agent 可同时发起多个 delegate_task（利用 DeepSeek 并行 tool calls）
- 子 Agent 不能递归委托（防止失控）

### 与 Hermes delegate_task 的区别
| 特性 | Hermes | YINYO v8.0 |
|------|--------|-----------|
| 子 Agent 隔离 | 独立进程 | 同进程独立循环 |
| 上下文共享 | 手动传 context | **自动继承父 Agent 完整对话** |
| 并行度 | 可配置 | 利用 DeepSeek 并行 tool calls |
| 复杂度 | 进程管理 + IPC | 纯内存循环 |

### 成本
子 Agent 的 ReAct 循环使用 **DeepSeek V4 Flash**（~$0.27/M tokens），并发执行 3 个子 Agent 各 20 步 ≈ $0.02。

---

## 3. Dual-Process + Temporal Tree Memory（重写 `memory.py` + `memory_tool.py`）

### 设计原则
**融合三大前沿**：Dual-Process (arXiv:2605.17625, 2026-05) + TiMem 时间树 (arXiv:2601.02845) + Mem0 Multi-Scope。

**Mem0 的根本局限**：只能追加记忆，不能让记忆**演化**。用户偏好会变、知识会更新，Mem0 会把旧事实和新事实都堆在那里。本方案用「事实生命周期 + 取代机制」解决这个问题。

### 3.1 三层架构

```
┌──────────────────────────────────────────────────────┐
│           PROCESS 1: Episodic (Working Memory)        │
│  DeepSeek 1M 上下文。最近 50 轮对话原样保留。         │
│  不压缩、不提取、不丢信息。成本 ≈ $0。                │
│  只在 token > 80% 时触发 Observation Masking。        │
└────────────────────────┬─────────────────────────────┘
                         │ 后台异步 (每次 run 结束)
                         ▼
┌──────────────────────────────────────────────────────┐
│         PROCESS 2: Semantic (Consolidated Memory)     │
│  LLM 扫描 情景记忆 → 提取事实 → 存入 TemporalTree。   │
│                                                      │
│  TemporalTree 结构（层级时间树）：                      │
│  User: 正元                                           │
│  ├── Preferences                                     │
│  │   ├── [v1 05-20] 偏好简洁回复 (conf:0.9)           │
│  │   └── [v2 05-25] 样式精度要求极高 (conf:0.95)      │
│  ├── Projects                                        │
│  │   └── YINYO                                       │
│  │       ├── [05-21] v3.0 转向纯ReAct (conf:1.0)     │
│  │       ├── [05-24] 认知层补齐 (conf:1.0)            │
│  │       └── [05-25] SUPSEDES ↑: v8.0 Dual-Process   │
│  └── Blood-Lessons                                   │
│       └── [05-23] 引用包前必验证 (conf:1.0)           │
│                                                      │
│  🔑 事实生命周期：created → confirmed → superseded → archived
│  v2 取代 v1：旧事实归档保留审计轨迹，但不参与检索       │
└────────────────────────┬─────────────────────────────┘
                         │ 查询时
                         ▼
┌──────────────────────────────────────────────────────┐
│          PROCESS 3: Retrieval (Multi-Scope)           │
│  查询时间加权 + 置信度加权 + Multi-Scope 过滤          │
│  - 时间衰减：越新的事实权重越高                         │
│  - 置信度优先：高置信度事实排在前面                     │
│  - scope 过滤：按 user_id / project / session 精确匹配 │
│  - 被取代的旧事实不参与检索（但可通过 audit_log 追溯） │
└──────────────────────────────────────────────────────┘
```

### 3.2 TemporalTree 数据结构

```python
@dataclass
class MemoryNode:
    id: str                    # mem_xxx
    content: str               # 事实内容
    category: str              # Preferences / Projects / Blood-Lessons / ...
    scopes: dict               # {user_id, project, session_id, type}
    confidence: float          # 0.0-1.0
    version: int               # 递增版本号
    status: str                # created / confirmed / superseded / archived
    superseded_by: str | None  # 被哪个节点取代
    supersedes: str | None     # 取代了哪个节点
    created_at: str
    updated_at: str
    access_count: int
    source_run_id: str         # 来源 run，用于审计追溯
    children: list             # 子节点（层级结构）
```

### 3.3 事实演化机制

```
创建：LLM 提取新事实 → status="created"
  ↓ (后续 run 中再次确认)
确认：同一事实再次出现 → confidence += 0.1, status="confirmed"
  ↓ (用户行为或明确声明变化)
取代：新事实与旧事实冲突 → 新节点 supersedes=旧节点id, 旧节点 superseded_by=新节点id
  旧事实 status="superseded"（归档但不删除）
  ↓ (长期未访问或显式清理)
归档：status="archived"（仅 audit_log 可见）
```

**对比 Mem0**：Mem0 只有「创建」没有「取代」。旧偏好和新偏好共存，Agent 不知道哪个是真的。

### 3.4 DeepSeek 深度适配

| DeepSeek 特性 | 利用方式 |
|-------------|---------|
| **1M 上下文** | Process 1 几乎零成本保留 50+ 轮对话原样 |
| **$0.27/M tokens** | Process 2 LLM 提取 ~$0.0003/次 |
| **并行 tool calls** | Process 3 检索时同时查 TemporalTree + VectorCache + 全文 |
| **Context Caching** | system prompt (SOUL+AGENTS+MEMORY) 自动缓存，重复注入零成本 |

### 3.5 跨 Session 检索

```
用户问："上次说的那个 bug 怎么修的？"
   │
   ├─ 1. TemporalTree 时间检索：按时间范围 + scope 精确匹配
   ├─ 2. VectorCache 语义搜索：TF-IDF 备选
   ├─ 3. Full-text grep：runs/*/summary.md 兜底
   └─ 4. 合并去重，时间排序，注入上下文
```

### 3.6 对比业界方案

| 特性 | Mem0 | TiMem | Dual-Process | YINYO v8.0 |
|------|------|-------|-------------|-----------|
| 层级时间树 | ❌ | ✅ | ❌ | ✅ |
| 事实演化（取代） | ❌ | ❌ | ❌ | ✅ |
| Multi-Scope | ✅ | ❌ | ❌ | ✅ |
| 双进程解耦 | ❌ | ❌ | ✅ | ✅ |
| 外部依赖 | SaaS | PostgreSQL | PostgreSQL | **零外部依赖** |
| 上下文污染防护 | ❌ | ❌ | 部分 | ✅（置信度衰减+来源追踪） |
| LoCoMo | 92.5 | 75.30 | - | 目标 90+ |

---

## 4. Provider Chain（修改 `model.py`，+50 行）

### 设计
```yaml
provider_chain:
  - provider: deepseek
    model: deepseek-v4-flash
    thinking: non-think
  - provider: deepseek
    model: deepseek-v4-pro
    thinking: think-high
  - provider: zhipu
    model: glm-4-flash
    api_key: ${GLM_API_KEY}
    base_url: https://open.bigmodel.cn/api/paas/v4
```

### 逻辑
```python
def chat_with_fallback(messages, tools, thinking):
    for provider in provider_chain:
        result = try_call(provider, messages, tools, thinking)
        if "error" not in result:
            return result
        # 记录降级
    return {"error": "All providers exhausted"}
```

**与 v7.0 的区别**：v7.0 只在 DeepSeek 内部降级（Flash→Pro）。v8.0 支持跨 provider 链。

---

## 5. Trace2Skill 闭环（重写 `evolution.py`，+150 行）

### 现状（v7.0）
- SkillCrystallizer: 工具序列哈希重复 3 次 → 结晶
- 缺：失败检测、自动加载、跨 session 融合

### v8.0 闭环
```
Task Failure
  │
  ├─ 1. 检测失败模式（同类任务连续 2 次失败）
  ├─ 2. LLM 分析失败原因 → 提取修复策略
  ├─ 3. 生成 SKILL.md（包含触发条件 + 步骤 + 常见陷阱）
  ├─ 4. 下次同类任务：
  │     ├─ Agent 检索 skills/ 目录
  │     ├─ 匹配触发条件 → 自动注入 skill 到 system prompt
  │     └─ 执行后更新 skill 成功率
  └─ 5. 跨 session 融合：同名 skill 合并，保留高成功率版本
```

### 新增函数
```python
class SkillEvolution:
    def detect_failure_pattern(self, recent_runs: list) -> list[FailurePattern]
    def extract_skill_from_failure(self, pattern: FailurePattern) -> Skill
    def auto_load_skills(self, task: str) -> list[Skill]  # 自动匹配
    def merge_skills(self, skill_a: Skill, skill_b: Skill) -> Skill  # 跨 session 融合
```

---

## 行数预算

| 文件 | v7.0 | v8.0 | 变化 |
|------|------|------|------|
| vision_adapter.py | ❌ | ~120 行 | **新增** |
| delegate.py | ❌ | ~200 行 | **新增** |
| memory.py | ~213 行 | ~450 行 | +237 行（TemporalTree + Dual-Process + LLM提取） |
| memory_tool.py | ~170 行 | ~250 行 | +80 行（scope + 演化操作 + 审计） |
| model.py | ~156 行 | ~206 行 | +50 行（provider_chain） |
| evolution.py | ~140 行 | ~290 行 | +150 行（Trace2Skill 闭环） |
| tools.py | ~200 行 | ~240 行 | +40 行（do_vision + delegate_task 注册） |
| agent.py | ~303 行 | ~340 行 | +37 行（skill auto-load + provider_chain 集成） |
| feishu_adapter.py | ~372 行 | ~400 行 | +28 行（图片消息检测） |
| **总计** | **~2,900 行** | **~4,140 行** | **+1,240 行** |

工具数：8 → **10**（+do_vision, +delegate_task）

---

## 关键设计决策

1. **为什么是 Dual-Process + TemporalTree 而不是 Mem0？** — Mem0 只能追加记忆，无法让记忆演化。用户偏好会变，旧事实应该被取代而不是和新事实共存。TemporalTree 用「创建→确认→取代→归档」生命周期 + 版本链解决这个问题。Mem0 是 2025 的答案，Dual-Process 是 2026.05 的答案。
2. **为什么 Process 1 保留 50 轮原始对话？** — DeepSeek V4 1M 上下文，50 轮 ≈ 15K tokens，占 1.5%。不压缩不提取，零信息损失。"量大了不起"就是 DeepSeek 的核心优势。
3. **为什么子 Agent 共享完整上下文？** — Cognition.ai 两原则：不共享上下文会导致子 Agent 做出冲突决策。多 Agent 架构的核心风险不是性能，是信息不对称。
4. **为什么 vision 用 adapter 而不是等 DeepSeek 原生支持？** — DeepSeek V4 无 Vision API，但飞书用户发截图是刚需。adapter 模式可随时替换为原生方案，不影响架构。

## 版本

v8.0 | 2026-05-25
