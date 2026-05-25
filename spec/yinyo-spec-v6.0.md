YINYO v5.0 → v6.0 变更 Spec
======================

## 变更概述

v6.0 补齐了 YINYO 作为独立 Agent 产品的**认知层**三个核心文件：
USER.md（用户画像）、MEMORY.md（持久记忆）、AGENTS.md（项目上下文）。

对标 Hermes 的 memory 系统设计：add/replace/remove 三个 action，target 分离 user 和 memory。

## 新增组件

### 1. memory_tool.py（~170 行）

对标 Hermes `memory` tool。提供：

| 函数 | 说明 |
|------|------|
| `memory_add(target, content, workspace)` | 添加记忆条目（带去重检测） |
| `memory_replace(target, old_text, content, workspace)` | 子串匹配替换（对标 Hermes） |
| `memory_remove(target, old_text, workspace)` | 子串匹配删除 |
| `load_memory_context(workspace)` | 加载 USER.md + MEMORY.md 用于 system prompt 注入 |
| `ensure_memory_files(workspace)` | 确保两个文件存在 |

**设计要点：**
- USER.md 1500 字符上限（~500 tokens）
- MEMORY.md 2200 字符上限（~800 tokens）
- § 分隔符拆分条目（对标 Hermes）
- 超出限制时自动合并最短条目
- 去重：前 80 字符相似即判重复
- replace/remove 用子串匹配，多个匹配时报 ambiguous

### 2. do_memory 工具（tools.py 新增）

```python
@tool(permission="ALLOW")
def do_memory(action: str, target: str, content: str = "", old_text: str = "") -> dict
```

注册为第 8 个原子工具。Agent 可通过 tool-calling 自主管理记忆。

### 3. agent.py 更新

**注入顺序（system prompt 从上到下）：**
```
AGENTS.md → MEMORY.md → USER.md → SOUL.md
```

每个注入块格式：
```
USER PROFILE [150/1500 chars]
==================================================
条目1
§
条目2
```

AGENTS.md 自动发现：优先 `.yinyo.md`，其次 `AGENTS.md`。

### 4. USER.md / MEMORY.md 模板

Agent 初始化时自动创建（如果不存在）：
- `USER.md`：`# USER.md — About the user`
- `MEMORY.md`：`# MEMORY.md — Agent's persistent notes`

## 工具数

7 → **8**（+do_memory）

## 行数预算

| 文件 | 变化 |
|------|------|
| memory_tool.py | +170 行（新增） |
| tools.py | +40 行（do_memory + 注册） |
| agent.py | +40 行（注入逻辑） |
| __init__.py | +10 行（导出） |
| **总计** | **+260 行，~2,700 行** |

## 对标检查

| 板块 | v5.0 | v6.0 |
|------|:----:|:----:|
| USER.md 用户画像 | ❌ | ✅ |
| MEMORY.md 持久记忆 | ❌ | ✅ |
| AGENTS.md 项目上下文 | ❌ | ✅ |
| SOUL.md 身份人格 | ✅ | ✅ |
| 记忆自管理（add/replace/remove） | ❌ | ✅ |
| 子串匹配 + 去重 | ❌ | ✅ |
| 字符上限 + 自动压缩 | ❌ | ✅ |
| 每次对话自动注入 | ❌ | ✅ |

## 版本

v6.0 | 2026-05-24
