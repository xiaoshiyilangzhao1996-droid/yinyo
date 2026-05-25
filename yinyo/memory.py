# memory.py — 5层记忆体系 v4.0（纯文件系统 + SHADOW + SimpleMem + VectorCache）
import os, json, shutil, re, math
from collections import defaultdict
from datetime import datetime, timezone

class MemoryStore:
    """5层记忆：L1 CORE / L2 EPISODIC / L3 SKILL / L4 CACHE / L5 SHADOW。"""
    def __init__(self, workspace: str):
        self.workspace = workspace
        self.l1_core = ["YINYO.md", "SOUL.md"]
        self._ensure_dirs()
        # ★ v4.0: L4 CACHE 向量检索
        cache_dir = os.path.join(workspace, "cache")
        self.vector_cache = VectorCache(cache_dir)

    def _ensure_dirs(self):
        for d in ["", "runs", "skills", "cache", "shadow"]:
            os.makedirs(os.path.join(self.workspace, d), exist_ok=True)

    # === L1: CORE ===
    def load_core(self) -> dict:
        core = {}
        for fname in self.l1_core:
            path = os.path.join(self.workspace, fname)
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as f:
                    core[fname] = f.read()
        return core

    # === L2: EPISODIC ===
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
            # ★ v4.0: 自动索引到向量缓存
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
        """★ v4.0: 语义检索历史任务（TF-IDF + Cosine Similarity）。"""
        return self.vector_cache.search(query, limit)

    # === L3: SKILLS ===
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

    # === L5: SHADOW ===
    def archive_shadow(self, run_id: str):
        src = os.path.join(self.workspace, "runs", run_id)
        dst = os.path.join(self.workspace, "shadow", run_id)
        if os.path.isdir(src) and not os.path.exists(dst):
            shutil.copytree(src, dst)
            with open(os.path.join(dst, ".archived"), "w") as f:
                f.write(datetime.now(timezone.utc).isoformat())


class SimpleMemCompressor:
    """信息熵过滤压缩器。"""

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


class VectorCache:
    """★ v4.0: 轻量语义检索。TF-IDF + Cosine Similarity。零外部依赖。
    
    设计原则（Less is more）：
    - 纯 Python stdlib（math, json, re, collections）
    - 零外部依赖，不使用 numpy / sklearn / sentence-transformers
    - 中英文混合分词（中文按字、英文按词）
    - 索引持久化到 JSON 文件
    - 对标 ByteRover (2025) 的 Context Tree 检索思路，但更轻量
    """

    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir
        self.index_path = os.path.join(cache_dir, "vector_index.json")
        self.documents: list[dict] = []
        os.makedirs(cache_dir, exist_ok=True)
        self._load()

    def add(self, doc_id: str, text: str, metadata: dict = None):
        """添加文档到索引。自动去重（同 id 覆盖）。"""
        # 去重
        self.documents = [d for d in self.documents if d["id"] != doc_id]
        self.documents.append({"id": doc_id, "text": text, "metadata": metadata or {}})
        self._save()

    def search(self, query: str, limit: int = 5) -> list[dict]:
        """语义搜索。返回 [(score, document), ...]"""
        if not self.documents:
            return []

        # 构建 corpus：[query, doc1, doc2, ...]
        corpus_texts = [d["text"] for d in self.documents]
        all_docs = [query] + corpus_texts

        # TF-IDF 向量化
        tfidf_vectors = self._compute_tfidf(all_docs)
        query_vec = tfidf_vectors[0]

        # Cosine Similarity
        scores = []
        for i, doc_vec in enumerate(tfidf_vectors[1:]):
            score = self._cosine_similarity(query_vec, doc_vec)
            if score > 0:
                scores.append((score, self.documents[i]))

        scores.sort(key=lambda x: x[0], reverse=True)
        return [{"score": round(s, 4), "id": d["id"], "text": d["text"][:200], "metadata": d["metadata"]}
                for s, d in scores[:limit]]

    def _compute_tfidf(self, docs: list[str]) -> list[dict]:
        """计算 TF-IDF 向量。"""
        tokenized = [self._tokenize(d) for d in docs]
        N = len(docs)

        # DF（文档频率）
        df = defaultdict(int)
        for tokens in tokenized:
            for t in set(tokens):
                df[t] += 1

        # TF-IDF per doc
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
        """Cosine similarity between two sparse vectors."""
        all_keys = set(a) | set(b)
        dot = sum(a.get(k, 0) * b.get(k, 0) for k in all_keys)
        norm_a = math.sqrt(sum(v ** 2 for v in a.values()))
        norm_b = math.sqrt(sum(v ** 2 for v in b.values()))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def _tokenize(self, text: str) -> list[str]:
        """中英文混合分词。中文逐字、英文逐词、数字保留。"""
        tokens = []
        for word in re.findall(r'[\u4e00-\u9fff]|[a-zA-Z]+|\d+', text.lower()):
            tokens.append(word)
        return tokens

    def _save(self):
        """持久化索引到 JSON。"""
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(self.documents, f, ensure_ascii=False, indent=2)

    def _load(self):
        """从 JSON 加载索引。"""
        if os.path.isfile(self.index_path):
            try:
                with open(self.index_path, "r", encoding="utf-8") as f:
                    self.documents = json.load(f)
            except (json.JSONDecodeError, IOError):
                self.documents = []
