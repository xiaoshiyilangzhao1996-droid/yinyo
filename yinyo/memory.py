# memory.py — Dual-Process + TemporalTree Memory v8.0
"""三层记忆架构：Episodic (原始对话) + Semantic (TemporalTree) + Retrieval (Multi-Scope)。

融合方案：Dual-Process (arXiv:2605.17625) + TiMem 时间树 (arXiv:2601.02845) + Mem0 Multi-Scope。
"""

import os, json, shutil, re, math, hashlib, uuid
from collections import defaultdict
from datetime import datetime, timezone
from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════
# MemoryNode — TemporalTree 节点
# ═══════════════════════════════════════════════════════

@dataclass
class MemoryNode:
    id: str                              # 唯一标识
    content: str                         # 事实内容
    category: str                        # 分类（Preferences / Projects / Blood-Lessons / ...）
    scopes: dict = field(default_factory=dict)  # {user_id, project, session_id, type}
    confidence: float = 0.5              # 置信度 0.0-1.0
    version: int = 1                     # 版本号
    status: str = "created"              # created / confirmed / superseded / archived
    superseded_by: str | None = None     # 被哪个节点取代
    supersedes: str | None = None        # 取代了哪个节点
    created_at: str = ""
    updated_at: str = ""
    access_count: int = 0
    source_run_id: str = ""              # 来源 run，审计追溯
    parent_id: str | None = None         # 父节点（层级结构）
    children: list = field(default_factory=list)  # 子节点 ID 列表

    def to_dict(self) -> dict:
        return {
            "id": self.id, "content": self.content, "category": self.category,
            "scopes": self.scopes, "confidence": self.confidence,
            "version": self.version, "status": self.status,
            "superseded_by": self.superseded_by, "supersedes": self.supersedes,
            "created_at": self.created_at, "updated_at": self.updated_at,
            "access_count": self.access_count, "source_run_id": self.source_run_id,
            "parent_id": self.parent_id, "children": self.children,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MemoryNode":
        return cls(
            id=d["id"], content=d["content"], category=d.get("category", "general"),
            scopes=d.get("scopes", {}), confidence=d.get("confidence", 0.5),
            version=d.get("version", 1), status=d.get("status", "created"),
            superseded_by=d.get("superseded_by"), supersedes=d.get("supersedes"),
            created_at=d.get("created_at", ""), updated_at=d.get("updated_at", ""),
            access_count=d.get("access_count", 0),
            source_run_id=d.get("source_run_id", ""),
            parent_id=d.get("parent_id"), children=d.get("children", []),
        )


# ═══════════════════════════════════════════════════════
# TemporalTree — 层级时间记忆树
# ═══════════════════════════════════════════════════════

class TemporalTree:
    """层级时间记忆树。

    结构示例：
    User: $NAME
    ├── Preferences
    │   ├── [v1] 偏好简洁回复 (conf:0.9)
    │   └── [v2] 样式精度要求高 (conf:0.95)
    └── Projects
        └── YINYO
            └── [v1] v3.0 转向纯ReAct (conf:1.0)
    """

    def __init__(self, tree_path: str):
        self.tree_path = tree_path
        self.nodes: dict[str, MemoryNode] = {}
        self.root_ids: list[str] = []  # 顶层节点
        self._load()

    # ── CRUD ──

    def add(self, content: str, category: str = "general",
            scopes: dict = None, confidence: float = 0.5,
            parent_id: str = None, source_run_id: str = "",
            check_supersede: bool = True) -> MemoryNode:
        """添加新节点。自动检测是否取代旧节点。"""
        node_id = "mem-" + uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()

        node = MemoryNode(
            id=node_id, content=content, category=category,
            scopes=scopes or {}, confidence=confidence,
            created_at=now, updated_at=now,
            source_run_id=source_run_id, parent_id=parent_id,
        )

        # 建树：挂到父节点下
        if parent_id and parent_id in self.nodes:
            self.nodes[parent_id].children.append(node_id)
        elif "/" in category:
            # 自动建层级：Preferences/Communication → 先建 Preferences，再挂子节点
            parts = category.split("/")
            current_parent = None
            for i, part in enumerate(parts):
                sub_cat = "/".join(parts[:i+1])
                existing = self._find_by_category(sub_cat)
                if existing:
                    current_parent = existing.id
                else:
                    cat_node = MemoryNode(
                        id="cat-" + uuid.uuid4().hex[:8],
                        content=part, category=sub_cat,
                        created_at=now, updated_at=now,
                        parent_id=current_parent,
                    )
                    self.nodes[cat_node.id] = cat_node
                    if current_parent:
                        self.nodes[current_parent].children.append(cat_node.id)
                    else:
                        self.root_ids.append(cat_node.id)
                    current_parent = cat_node.id
            node.parent_id = current_parent
            if current_parent:
                self.nodes[current_parent].children.append(node_id)
        else:
            self.root_ids.append(node_id)

        # 检测冲突：查找同类同 scope 的现有事实，判断是否取代
        if check_supersede:
            existing = self._find_conflict(node)
            if existing:
                # 新事实取代旧事实
                node.version = existing.version + 1
                node.supersedes = existing.id
                node.confidence = max(node.confidence, existing.confidence + 0.1)
                existing.status = "superseded"
                existing.superseded_by = node_id

        self.nodes[node_id] = node
        self._save()
        return node

    def confirm(self, node_id: str) -> MemoryNode | None:
        """确认已有事实，提升置信度。"""
        if node_id not in self.nodes:
            return None
        node = self.nodes[node_id]
        node.confidence = min(1.0, node.confidence + 0.1)
        node.status = "confirmed"
        node.updated_at = datetime.now(timezone.utc).isoformat()
        node.access_count += 1
        self._save()
        return node

    def supersede(self, old_id: str, new_content: str, source_run_id: str = "") -> MemoryNode | None:
        """用新事实取代旧事实。"""
        if old_id not in self.nodes:
            return None
        old = self.nodes[old_id]
        return self.add(
            content=new_content, category=old.category,
            scopes=old.scopes, confidence=old.confidence,
            parent_id=old.parent_id, source_run_id=source_run_id,
        )

    def archive(self, node_id: str):
        """归档节点（不删除，仅标记）。"""
        if node_id in self.nodes:
            self.nodes[node_id].status = "archived"
            self._save()

    # ── 检索 ──

    def search(self, query: str, scopes: dict = None, limit: int = 5,
               time_decay: float = 0.01) -> list[MemoryNode]:
        """Multi-Scope + 时间加权检索。

        Args:
            query: 搜索查询
            scopes: scope 过滤条件
            limit: 返回条数
            time_decay: 时间衰减系数（每天衰减的比例）
        """
        candidates = []
        now = datetime.now(timezone.utc)

        for node in self.nodes.values():
            # 排除非活跃节点
            if node.status in ("superseded", "archived"):
                continue
            # 排除纯分类节点（没有实际内容或 id 以 cat- 开头）
            if node.id.startswith("cat-"):
                continue
            # scope 过滤
            if scopes and not self._match_scopes(node.scopes, scopes):
                continue
            candidates.append(node)

        # 打分：语义匹配 + 时间衰减 + 置信度
        scored = []
        query_tokens = set(self._tokenize(query))
        for node in candidates:
            content_tokens = set(self._tokenize(node.content))
            # Jaccard 相似度（零外部依赖）
            intersection = query_tokens & content_tokens
            union = query_tokens | content_tokens
            semantic_score = len(intersection) / max(len(union), 1)

            # 时间衰减
            try:
                created = datetime.fromisoformat(node.created_at)
                days_ago = (now - created).total_seconds() / 86400
                time_score = math.exp(-time_decay * days_ago)
            except Exception:
                time_score = 0.5

            # 综合分数
            score = (0.5 * semantic_score + 0.3 * node.confidence + 0.2 * time_score)
            scored.append((score, node))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [node for _, node in scored[:limit]]

    def get_active_nodes(self, category: str = None) -> list[MemoryNode]:
        """获取所有活跃（非取代/归档）节点。"""
        result = []
        for node in self.nodes.values():
            if node.status in ("superseded", "archived"):
                continue
            if node.id.startswith("cat-"):
                continue
            if category and node.category != category:
                continue
            result.append(node)
        return sorted(result, key=lambda n: n.created_at, reverse=True)

    def get_audit_trail(self, node_id: str) -> list[MemoryNode]:
        """追溯一个事实的完整版本链。"""
        if node_id not in self.nodes:
            return []
        trail = [self.nodes[node_id]]
        current = self.nodes[node_id]

        # 向前追溯
        while current.supersedes and current.supersedes in self.nodes:
            current = self.nodes[current.supersedes]
            trail.insert(0, current)

        # 向后追溯
        current = self.nodes[node_id]
        while current.superseded_by and current.superseded_by in self.nodes:
            current = self.nodes[current.superseded_by]
            trail.append(current)

        return trail

    # ── 序列化 ──

    def _save(self):
        os.makedirs(os.path.dirname(self.tree_path), exist_ok=True)
        data = {
            "root_ids": self.root_ids,
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(self.tree_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load(self):
        if not os.path.isfile(self.tree_path):
            return
        try:
            with open(self.tree_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.root_ids = data.get("root_ids", [])
            self.nodes = {k: MemoryNode.from_dict(v) for k, v in data.get("nodes", {}).items()}
        except (json.JSONDecodeError, KeyError):
            self.nodes = {}
            self.root_ids = []

    # ── 内部辅助 ──

    def _find_conflict(self, new_node: MemoryNode) -> MemoryNode | None:
        """检测是否有现有事实与新事实冲突（同类同scope，语义相似）。"""
        for node in self.nodes.values():
            if node.status in ("superseded", "archived"):
                continue
            if node.id.startswith("cat-"):
                continue
            if node.id == new_node.id:
                continue
            if node.category != new_node.category:
                continue
            if not self._match_scopes(node.scopes, new_node.scopes):
                continue
            # 简单语义相似度检测
            similarity = self._jaccard_similarity(node.content, new_node.content)
            if similarity > 0.3:
                return node
        return None

    def _find_by_category(self, category: str) -> MemoryNode | None:
        for node in self.nodes.values():
            if node.category == category and node.id.startswith("cat-"):
                return node
        return None

    def _match_scopes(self, node_scopes: dict, query_scopes: dict) -> bool:
        """检查 node 的 scopes 是否匹配查询条件。"""
        for key, val in query_scopes.items():
            if key not in node_scopes:
                return False
            if node_scopes[key] != val:
                return False
        return True

    def _tokenize(self, text: str) -> list[str]:
        """中英文混合分词。"""
        tokens = []
        for word in re.findall(r'[\u4e00-\u9fff]|[a-zA-Z]+|\d+', text.lower()):
            tokens.append(word)
        return tokens

    def _jaccard_similarity(self, a: str, b: str) -> float:
        set_a = set(self._tokenize(a))
        set_b = set(self._tokenize(b))
        if not set_a or not set_b:
            return 0.0
        return len(set_a & set_b) / len(set_a | set_b)


# ═══════════════════════════════════════════════════════
# VectorCache — 轻量语义检索引擎（保留自 v4.0）
# ═══════════════════════════════════════════════════════

class VectorCache:
    """轻量语义检索。TF-IDF + Cosine Similarity。零外部依赖。"""

    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir
        self.index_path = os.path.join(cache_dir, "vector_index.json")
        self.documents: list[dict] = []
        os.makedirs(cache_dir, exist_ok=True)
        self._load()

    def add(self, doc_id: str, text: str, metadata: dict = None):
        self.documents = [d for d in self.documents if d["id"] != doc_id]
        self.documents.append({"id": doc_id, "text": text, "metadata": metadata or {}})
        self._save()

    def search(self, query: str, limit: int = 5) -> list[dict]:
        if not self.documents:
            return []
        corpus_texts = [d["text"] for d in self.documents]
        all_docs = [query] + corpus_texts
        tfidf_vectors = self._compute_tfidf(all_docs)
        query_vec = tfidf_vectors[0]
        scores = []
        for i, doc_vec in enumerate(tfidf_vectors[1:]):
            score = self._cosine_similarity(query_vec, doc_vec)
            if score > 0:
                scores.append((score, self.documents[i]))
        scores.sort(key=lambda x: x[0], reverse=True)
        return [{"score": round(s, 4), "id": d["id"], "text": d["text"][:200],
                 "metadata": d["metadata"]} for s, d in scores[:limit]]

    def _compute_tfidf(self, docs: list[str]) -> list[dict]:
        tokenized = [self._tokenize(d) for d in docs]
        N = len(docs)
        df = defaultdict(int)
        for tokens in tokenized:
            for t in set(tokens):
                df[t] += 1
        vectors = []
        for tokens in tokenized:
            tf = defaultdict(int)
            for t in tokens:
                tf[t] += 1
            vec = {}
            for t, count in tf.items():
                vec[t] = count * (math.log((N + 1) / (df[t] + 1)) + 1)
            vectors.append(vec)
        return vectors

    def _cosine_similarity(self, a: dict, b: dict) -> float:
        all_keys = set(a) | set(b)
        dot = sum(a.get(k, 0) * b.get(k, 0) for k in all_keys)
        norm_a = math.sqrt(sum(v ** 2 for v in a.values()))
        norm_b = math.sqrt(sum(v ** 2 for v in b.values()))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def _tokenize(self, text: str) -> list[str]:
        tokens = []
        for word in re.findall(r'[\u4e00-\u9fff]|[a-zA-Z]+|\d+', text.lower()):
            tokens.append(word)
        return tokens

    def _save(self):
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(self.documents, f, ensure_ascii=False, indent=2)

    def _load(self):
        if os.path.isfile(self.index_path):
            try:
                with open(self.index_path, "r", encoding="utf-8") as f:
                    self.documents = json.load(f)
            except (json.JSONDecodeError, IOError):
                self.documents = []


# ═══════════════════════════════════════════════════════
# FactExtractor — LLM 事实提取器
# ═══════════════════════════════════════════════════════

class FactExtractor:
    """用 LLM 从对话中提取值得记住的事实。"""

    def __init__(self, model=None):
        self.model = model

    def extract(self, messages: list, existing_tree: TemporalTree = None) -> list[dict]:
        """从对话消息中提取事实。

        Returns:
            [{content, category, confidence, supersedes_id}, ...]
        """
        if not self.model:
            return []

        # 构建提取 prompt
        recent = []
        for m in messages[-20:]:
            role = m.get("role", "")
            content = str(m.get("content", ""))[:200]
            if role in ("user", "assistant"):
                recent.append(f"[{role.upper()}] {content}")

        # 获取已有事实摘要（用于去重和冲突检测）
        existing_summary = ""
        if existing_tree:
            active = existing_tree.get_active_nodes()
            if active:
                existing_summary = "Existing facts:\n" + "\n".join(
                    f"- [{n.category}] {n.content} (conf:{n.confidence:.1f})"
                    for n in active[:10]
                )

        prompt = (
            "Extract 1-3 key facts from this conversation that are worth remembering. "
            "Output ONLY a JSON array. Each fact has: content (string), category (one of: "
            "Preferences, Projects, Knowledge, Blood-Lessons, Anti-Patterns, General), "
            "confidence (0.0-1.0), supersedes (string or null if no existing fact to replace).\n\n"
            + existing_summary
            + "\n\nRecent conversation:\n" + "\n".join(recent[-15:])
        )

        try:
            resp = self.model.chat(
                messages=[{"role": "user", "content": prompt}],
                tools=None, max_tokens=500
            )
            text = resp.get("content", "")
            # 提取 JSON 数组
            start = text.find("[")
            end = text.rfind("]")
            if start >= 0 and end > start:
                facts = json.loads(text[start:end+1])
                return facts
        except Exception:
            pass
        return []


# ═══════════════════════════════════════════════════════
# MemoryStore — 统一记忆存储（整合 TemporalTree + VectorCache + Episodic）
# ═══════════════════════════════════════════════════════

class SimpleMemCompressor:
    """信息熵过滤压缩器（保留自 v4.0）。"""
    def compress(self, history: list, max_tokens: int = 3000) -> list:
        if len(history) <= 10:
            return history
        scored = [(self._entropy(str(m)), m) for m in history]
        scored.sort(key=lambda x: x[0], reverse=True)
        keep = max(int(len(scored) * 0.6), 10)
        return [m for _, m in scored[:keep]]

    def _entropy(self, text: str) -> float:
        if not text: return 0.0
        freq = {}
        for c in text:
            freq[c] = freq.get(c, 0) + 1
        total = len(text)
        return -sum((n/total) * math.log2(n/total) for n in freq.values() if n > 0)


class MemoryStore:
    """统一记忆存储。整合三层架构。"""

    def __init__(self, workspace: str):
        self.workspace = workspace
        cache_dir = os.path.join(workspace, "cache")
        os.makedirs(cache_dir, exist_ok=True)

        # TemporalTree（Process 2: Semantic）
        self.tree = TemporalTree(os.path.join(cache_dir, "temporal_tree.json"))

        # VectorCache（Process 3: Retrieval 辅助）
        self.vector_cache = VectorCache(cache_dir)

        # FactExtractor（LLM 驱动）
        self._extractor: FactExtractor | None = None

        # L1 CORE
        self.l1_core = ["YINYO.md", "SOUL.md"]

        self._ensure_dirs()

    def _ensure_dirs(self):
        for d in ["", "runs", "skills", "cache", "shadow"]:
            os.makedirs(os.path.join(self.workspace, d), exist_ok=True)

    def set_model(self, model):
        """注入 ModelGateway 用于 LLM 事实提取。"""
        self._extractor = FactExtractor(model)

    # ── L1: CORE ──

    def load_core(self) -> dict:
        core = {}
        for fname in self.l1_core:
            path = os.path.join(self.workspace, fname)
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as f:
                    core[fname] = f.read()
        return core

    # ── Process 2: Semantic（TemporalTree） ──

    def add_fact(self, content: str, category: str = "general",
                 scopes: dict = None, confidence: float = 0.5,
                 source_run_id: str = "") -> MemoryNode:
        return self.tree.add(content, category, scopes, confidence,
                            source_run_id=source_run_id)

    def extract_and_store(self, messages: list, run_id: str):
        """LLM 提取事实 → 存入 TemporalTree。"""
        if not self._extractor:
            return
        facts = self._extractor.extract(messages, self.tree)
        for f in facts:
            self.tree.add(
                content=f.get("content", ""),
                category=f.get("category", "General"),
                confidence=f.get("confidence", 0.5),
                source_run_id=run_id,
            )

    def search_memory(self, query: str, scopes: dict = None, limit: int = 5) -> list[MemoryNode]:
        return self.tree.search(query, scopes, limit)

    def get_memory_summary(self, max_chars: int = 10000) -> str:
        """生成 MEMORY.md 格式的摘要（用于 system prompt 注入）。"""
        active = self.tree.get_active_nodes()
        if not active:
            return ""

        # 按分类分组
        by_category: dict[str, list[MemoryNode]] = defaultdict(list)
        for n in active:
            by_category[n.category].append(n)

        lines = []
        for cat, nodes in sorted(by_category.items()):
            lines.append(f"### {cat}")
            for n in sorted(nodes, key=lambda x: x.confidence, reverse=True):
                lines.append(f"- [{n.status}] {n.content} (conf:{n.confidence:.1f}, v{n.version})")
            lines.append("")

        summary = "\n".join(lines)
        if len(summary) > max_chars:
            summary = summary[:max_chars-100] + "\n\n... (truncated)"
        return summary

    # ── L2: EPISODIC ──

    def save_episodic(self, run_id: str, evidence: list, summary: str = ""):
        run_dir = os.path.join(self.workspace, "runs", run_id)
        os.makedirs(run_dir, exist_ok=True)

        if evidence:
            compressor = SimpleMemCompressor()
            compressed = compressor.compress(evidence, max_tokens=2000)
        else:
            compressed = evidence

        if summary:
            comp_note = f"\nCompressed {len(evidence)}→{len(compressed)} items" if evidence else ""
            with open(os.path.join(run_dir, "summary.md"), "w", encoding="utf-8") as f:
                f.write(f"# Run {run_id}\n\n{summary}{comp_note}\n")
            self.vector_cache.add(run_id, summary, {"type": "episodic"})

    def list_episodic(self, limit: int = 10) -> list:
        runs_dir = os.path.join(self.workspace, "runs")
        if not os.path.isdir(runs_dir): return []
        runs = sorted(
            [d for d in os.listdir(runs_dir)
             if os.path.isdir(os.path.join(runs_dir, d))],
            reverse=True
        )
        result = []
        for rid in runs[:limit]:
            mpath = os.path.join(runs_dir, rid, "manifest.json")
            if os.path.isfile(mpath):
                with open(mpath) as f:
                    result.append({"run_id": rid, **json.load(f)})
        return result

    def search_semantic(self, query: str, limit: int = 5) -> list:
        return self.vector_cache.search(query, limit)

    # ── L3: SKILLS ──

    def list_skills(self) -> list:
        skills_dir = os.path.join(self.workspace, "skills")
        if not os.path.isdir(skills_dir): return []
        skills = []
        for name in os.listdir(skills_dir):
            spath = os.path.join(skills_dir, name)
            if os.path.isdir(spath):
                mp = os.path.join(spath, "meta.json")
                if os.path.isfile(mp):
                    with open(mp) as f:
                        skills.append(json.load(f))
        return skills

    # ── L5: SHADOW ──

    def archive_shadow(self, run_id: str):
        src = os.path.join(self.workspace, "runs", run_id)
        dst = os.path.join(self.workspace, "shadow", run_id)
        if os.path.isdir(src) and not os.path.exists(dst):
            shutil.copytree(src, dst)
            with open(os.path.join(dst, ".archived"), "w") as f:
                f.write(datetime.now(timezone.utc).isoformat())
