# context.py — Context Manager v8.1（LLM 结构化压缩 + DeepSeek 高适配）
import os, json
from datetime import datetime, timezone

class ContextManager:
    """三层上下文管理：Observation Masking → LLM DAG Compression → Memory Retrieval。
    v7.0: 压缩改为 LLM 结构化摘要（DeepSeek 极便宜，不用规则）。"""

    def __init__(self, max_tokens: int = 50000, keep_tail: int = 64, cache_dir: str = "cache"):
        self.max_tokens = max_tokens      # v7.0: 25K→50K（128K窗口充分使用）
        self.keep_tail = keep_tail
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self._dag_nodes = []
        self.messages: list = []
        self._model = None                # LLM 压缩器（agent 注入）
        self._compress_count = 0          # 压缩次数（控制频率）

    def set_model(self, model):
        """注入 ModelGateway 用于 LLM 压缩。"""
        self._model = model

    def auto_manage(self, step: int):
        """每步自动检查并触发对应的升降层。v7.0: 阈值放宽。"""
        estimated = self._estimate_tokens()
        budget = self.max_tokens

        # Layer 1: Observation Masking（token > 80%，v7.0 放宽）
        if estimated > budget * 0.8:
            self.messages = self.mask_observations(self.messages, keep_recent=8)

        # Layer 2: LLM DAG Compression（token > 90%，v7.0 放宽）
        if estimated > budget * 0.9 and self._model and self._compress_count < 3:
            self._compress_count += 1
            self.messages = self.compress(self.messages)

        return estimated

    def get_messages(self) -> list:
        return self.messages

    def add(self, message: dict):
        self.messages.append(message)

    def compress(self, messages: list) -> list:
        """压缩失败 = 原样返回，绝不丢消息（铁律 1）。v7.0: LLM 结构化摘要。"""
        if len(messages) < self.keep_tail:
            return messages
        try:
            summary = self._generate_summary(messages[:-self.keep_tail])
            if not summary:
                return messages
            self._write_dag_node(summary, len(messages[:-self.keep_tail]))
            return [{"role": "system", "content": summary}] + messages[-self.keep_tail:]
        except Exception:
            return messages

    def mask_observations(self, messages: list, keep_recent: int = 8) -> list:
        """Layer 1: 保留最近 N 个 tool 输出。v7.0: 5→8（窗口大了）。"""
        result = []
        tool_count = 0
        for msg in reversed(messages):
            role = msg.get("role", "") if isinstance(msg, dict) else ""
            if role == "tool":
                tool_count += 1
                if tool_count <= keep_recent:
                    result.insert(0, msg)
                else:
                    result.insert(0, {"role": "system", "content": "[Observation masked: older tool output omitted]"})
            else:
                result.insert(0, msg)
        return result

    def retrieve_memory(self, memory_store, query: str = "", limit: int = 5) -> list:
        """Layer 3: 语义检索历史记忆。"""
        if not query:
            episodic = memory_store.list_episodic(limit)
            return [{"role": "system",
                     "content": f"[Memory: Run {e.get('run_id','')} — {e.get('task','')[:100]}]"}
                    for e in episodic[:3]]
        results = memory_store.search_semantic(query, limit)
        if not results:
            return []
        return [{"role": "system",
                 "content": f"[Memory (score={r['score']}): {r['id']} — {r['text'][:150]}]"}
                for r in results[:3]]

    def should_search_sessions(self, user_msg: str, context: list) -> bool:
        triggers = ["上次", "之前", "历史", "记得", "聊过", "查一下",
                    "那个 bug", "那个文件", "怎么修的"]
        if not any(t in user_msg for t in triggers):
            return False
        if self._answerable_from_context(user_msg, context):
            return False
        return True

    def _estimate_tokens(self) -> int:
        total = 0
        for m in self.messages:
            if isinstance(m, dict):
                content = str(m.get("content", ""))
                cn = sum(1 for c in content if '\u4e00' <= c <= '\u9fff')
                en = len(content) - cn
                total += cn + int(en * 0.25)
        return total

    def _generate_summary(self, messages: list) -> str:
        """v7.0: LLM 生成结构化压缩摘要。失败回退到关键词提取。
        
        ACON 简化版: 用模型分析消息 → 输出 {decisions, files_changed, errors, state}。
        """
        # 尝试 LLM 压缩
        if self._model:
            try:
                return self._llm_compress(messages)
            except Exception:
                pass
        # 回退: 关键词提取
        return self._keyword_compress(messages)

    def _llm_compress(self, messages: list) -> str:
        """LLM 结构化压缩。成本 ~$0.0003/次（DeepSeek V4-Flash）。"""
        # 提取关键消息（用户输入 + assistant 回复 + tool 结果摘要）
        excerpt = []
        for m in messages[-30:]:  # 最近 30 条
            if not isinstance(m, dict):
                continue
            role = m.get("role", "")
            content = str(m.get("content", ""))
            if role == "user":
                excerpt.append(f"[USER] {content[:200]}")
            elif role == "assistant":
                excerpt.append(f"[ASSISTANT] {content[:200]}")
            elif role == "tool":
                excerpt.append(f"[TOOL RESULT] {content[:150]}")

        prompt = (
            "Compress the following conversation excerpt into a structured summary. "
            "Output ONLY a JSON object with these fields:\n"
            "- decisions: key decisions made (list of strings)\n"
            "- files_changed: files modified (list of strings, empty if none)\n"
            "- errors: errors encountered (list of strings, empty if none)\n"
            "- state: current task state / progress (one sentence)\n\n"
            "Conversation excerpt:\n" + "\n".join(excerpt[-20:])
        )
        try:
            resp = self._model.chat(
                messages=[{"role": "user", "content": prompt}],
                tools=None,
                max_tokens=300
            )
            text = resp.get("content", "")
            if text:
                # 验证是合法 JSON
                data = json.loads(text)
                return (
                    f"[Compressed: {len(messages)} msgs] "
                    f"Decisions: {'; '.join(data.get('decisions', [])[:3])}. "
                    f"Files: {', '.join(data.get('files_changed', [])[:3]) or 'none'}. "
                    f"Errors: {', '.join(data.get('errors', [])[:2]) or 'none'}. "
                    f"State: {data.get('state', 'ongoing')}"
                )
        except Exception:
            pass
        return self._keyword_compress(messages)

    def _keyword_compress(self, messages: list) -> str:
        """回退: 关键词提取。"""
        user_msgs = [m for m in messages if isinstance(m, dict) and m.get("role") == "user"]
        if not user_msgs:
            return ""
        topics = set()
        for m in user_msgs[-10:]:
            topics.add(str(m.get("content", ""))[:50])
        return f"[Compressed: {len(messages)} messages. Topics: {'; '.join(list(topics)[:5])}]"

    def _write_dag_node(self, summary: str, msg_count: int):
        node = {"ts": datetime.now(timezone.utc).isoformat(),
                "msg_count": msg_count, "summary": summary}
        self._dag_nodes.append(node)
        with open(os.path.join(self.cache_dir, "lcm.db"), "a", encoding="utf-8") as f:
            f.write(json.dumps(node, ensure_ascii=False) + "\n")

    def _answerable_from_context(self, user_msg: str, context: list) -> bool:
        keywords = set(user_msg.lower().split())
        context_text = " ".join(str(m.get("content", "")) for m in context[-10:] if isinstance(m, dict))
        matches = sum(1 for kw in keywords if kw in context_text.lower())
        return matches >= 2

    def budget_allocator(self, step: int) -> dict:
        return {"system_prompt": 4000, "recent_turns": 15000, "dag_summaries": 5000,
                "core_memory": 3000, "tool_output": 15000, "total": 50000}
