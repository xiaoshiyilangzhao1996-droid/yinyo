YINYO v6.0 → v7.0 变更 Spec
======================

## 变更概述

v7.0 三件事：
1. **LLM 结构化压缩** — 上下文压缩从关键词提取升级为 LLM 驱动（ACON 简化版）
2. **自动反思系统** — 每次 run 结束 LLM 反思 + 每 10 次 run 深度反思
3. **AGENTS.md 开发宪章** — Karpathy 原则 + skill-schema 准则 + 血泪教训精炼为行为指令

核心动机：DeepSeek V4 极便宜，"每层都用 LLM"取代规则。

## 变更详情

### 1. context.py — LLM 结构化压缩

| 项目 | v6.0 | v7.0 |
|------|------|------|
| max_tokens | 25,000 | **50,000**（128K 窗口充分使用） |
| keep_tail | 32 | **64** |
| 压缩方式 | 规则关键词提取 | **LLM 结构化摘要（ACON 简化版）** |
| Observation Masking 阈值 | token > 70% | token > **80%** |
| LLM 压缩阈值 | token > 85% | token > **90%** |
| LLM 压缩器 | ❌ | `set_model()` 注入 ModelGateway |

`_llm_compress()` 新增（~50 行）：
- 取最近 30 条消息 → 提取 user/assistant/tool 摘要
- 请求 LLM 输出 JSON: {decisions, files_changed, errors, state}
- 格式化: `[Compressed: N msgs] Decisions: ... Files: ... Errors: ... State: ...`
- 成本: ~$0.0003/次（DeepSeek V4-Flash）
- 失败回退到 `_keyword_compress()`

`_keyword_compress()` 重构为纯回退方案（~10 行）。

### 2. agent.py — 自动反思系统

**auto-reflect** (`_reflect_on_run`, ~37 行)：
- 每次 run 结束后自动触发
- 输入: task + summary + 最近 5 条 evidence + 当前 MEMORY.md
- LLM 输出 JSON: {reflections, memory_add, memory_update, memory_remove}
- 自动执行 memory_add/replace/remove
- 反思写入 `runs/{run_id}/reflection.md`
- 反思加入 VectorCache 供后续语义检索
- 成本: ~$0.0005/次

**deep-reflect** (`_deep_reflect`, ~32 行)：
- 每 10 次 run 触发
- 扫描最近 10 次 run 的 reflection.md
- LLM 分析 pattern / anti-pattern / user_trends
- 自动更新 MEMORY.md（标记 [ANTI-PATTERN]）
- 记录到 change_manifest
- 成本: ~$0.002/次

**其他变更：**
- `run_count` 计数器追踪 run 次数
- `set_model()` 注入到 context 用于 LLM 压缩
- `run()` 返回值新增 `reflection` 字段

### 3. AGENTS.md — 开发宪章（新增）

位置: `yinyo/AGENTS.md`（~70 行），同时复制到 `test_ws/AGENTS.md`

内容结构：
- **验证优先** — 写前读代码、用前查文档、引用包前上 PyPI/GitHub 确认（🔴 `agentmemory` 血训）
- **Spec = 代码** — 不一致 = 技术债
- **不自审** — 独立盲测（🔴 v2.1: 48.9% → v3.0+: 100%）
- **产品视角** — 从产品板块设计，不是技术组件堆砌（🔴 v5.0 前漏了认知层三文件）
- **样式精度** — 逐项对标，差不多 = 重做
- **行为准则** — 简单优先、出错就认、不编造确认、落盘才闭环

注入方式：agent.py 第 112-118 行自动发现 `AGENTS.md` / `.yinyo.md`，截取 1500 字符注入 system prompt。

## 行数预算

| 文件 | v6.0 | v7.0 | 变化 |
|------|------|------|------|
| context.py | ~190 行 | ~192 行 | +2 行（LLM 压缩重构，净增少） |
| agent.py | ~224 行 | ~303 行 | +79 行（reflect 系统） |
| AGENTS.md | ❌ | ~70 行 | 新增 |
| **总计** | **~2,700 行** | **~2,900 行** | **+200 行** |

## 关键设计决策

1. **为什么 LLM 压缩？** — DeepSeek V4 Flash $0.27/M tokens，一次压缩 $0.0003。规则压缩长期质量差，LLM 压缩每句话都是语义级摘要。
2. **为什么 auto-reflect？** — Claude Diary/Codex MEMORY 模式证明：每次任务后让 LLM 反思"什么值得记住"，能持续积累高质量记忆。
3. **为什么 deep-reflect？** — 单次反思粒度太细。每 10 次 run 跨会话扫描 patterns，发现重复错误和用户趋势。
4. **为什么 AGENTS.md？** — SOUL.md 是身份，AGENTS.md 是方法。嵌入开发原则到 system prompt，让 YINYO 每次执行都遵循同一套纪律。

## 盲测结果

v7.0 盲测通过率: **100%**（保持 v4.0+ 连续满分）

## 版本

v7.0 | 2026-05-25
