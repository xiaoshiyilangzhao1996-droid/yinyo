YINYO v8.0 → v8.1 变更 Spec
==============================

## 变更概述

v8.1 是 YINYO 化的轻量工程层。取 AHE 之神（变更可追溯、失败闭环、验证自动化），用 DeepSeek 之器（LLM 替代规则引擎）。

**不是搬 AHE 的完整体系，而是吸收其核心价值，做到最简实现。**

## 对标 AHE

| AHE 核心价值 | YINYO v8.1 实现 | 方式 |
|-------------|---------------|------|
| 变更可追溯 | 每次 run 结束 LLM 自动生成 Change Manifest | ~$0.0003/run |
| 失败闭环 | 盲测通过 → verified/keep；失败 → reverted/revert | 自动状态流转 |
| 验证自动化 | `verify_manifest()` + `get_latest_verified_run()` | 无需人工填写 |

## 变更详情

### 1. ChangeManifest 升级（evolution.py +90 行）

新增三个方法和结构化 manifest 格式：

```python
class ChangeManifest:
    def create_manifest(run_id, change_type, summary, affected_files, blind_test_result) -> dict
    def get_latest_verified_run() -> str | None   # 回滚用
    def list_manifests(status=None, limit=20) -> list[dict]
```

Manifest 生命周期：`draft → (盲测) → verified/reverted`

Manifest JSON 格式：
```json
{
  "manifest_id": "m-r-20260525-xxx",
  "run_id": "r-20260525-xxx",
  "ts": "2026-05-25T10:00:00Z",
  "change_type": "feat",
  "summary": "LLM 自动生成的变更摘要",
  "affected_files": ["yinyo/memory.py", "yinyo/agent.py"],
  "status": "verified",
  "verdict": "keep",
  "blind_test": {"status": "pass", "pass_rate": "12/12"}
}
```

### 2. agent.py 新增两个方法（+87 行）

**`_auto_manifest()`** — 每次 run 结束后自动调用：
- 检测是否有工具调用（纯对话跳过）
- 提取受影响的文件
- LLM 生成变更摘要（~$0.0003）
- 创建 draft manifest

**`verify_manifest()`** — 盲测完成后调用：
- 盲测通过 → status="verified", verdict="keep"
- 盲测失败 → status="reverted", verdict="revert"
- 自动记录到 changes.jsonl

### 3. 不做什么（Less is more）

- ❌ 不引入 HARNESS.md 规范文件
- ❌ 不引入 4 个审计脚本 + 4 种 profile
- ❌ 不引入 JSON Schema 验证
- ❌ 不引入 experience observability 模板（YINYO 已有 detect_failure_pattern）

## 行数预算

| 文件 | v8.0 | v8.1 | 变化 |
|------|------|------|------|
| evolution.py | ~374 行 | ~464 行 | +90 行（ChangeManifest 升级） |
| agent.py | ~364 行 | ~451 行 | +87 行（_auto_manifest + verify_manifest） |
| **总计** | **~5,200 行** | **~5,380 行** | **+177 行** |

成本：每次 run 额外 $0.0003（LLM 生成摘要）。纯对话 run 跳过（零额外成本）。

## 版本

v8.1 | 2026-05-25
