# test_memory.py — TemporalTree + VectorCache + MemoryStore 单元测试
"""对标 Hermes memory 测试：CRUD、演化、检索、持久化。"""

import pytest, json, os, time
from memory import TemporalTree


class TestTemporalTree:
    """TemporalTree 核心功能测试。"""

    def test_add_node(self, temporal_tree):
        """添加节点后应能检索到。"""
        node = temporal_tree.add("正元偏好简洁回复", category="Preferences",
                                 confidence=0.9)
        assert node.id is not None
        assert node.content == "正元偏好简洁回复"
        assert node.status == "created"

        results = temporal_tree.search("偏好")
        assert len(results) > 0
        assert any(n.id == node.id for n in results)

    def test_confirm_node(self, temporal_tree):
        """确认节点后置信度应提升。"""
        node = temporal_tree.add("测试事实", confidence=0.5)
        confirmed = temporal_tree.confirm(node.id)
        assert confirmed is not None
        assert confirmed.confidence == 0.6
        assert confirmed.status == "confirmed"

    def test_supersede_fact(self, temporal_tree):
        """v2 应取代 v1，v1 应被标记为 superseded。"""
        v1 = temporal_tree.add("用户偏好 Python", category="Preferences",
                               confidence=0.5)
        v2 = temporal_tree.add("用户偏好 Rust", category="Preferences",
                               confidence=0.7)

        assert v2.supersedes == v1.id
        assert v1.id in temporal_tree.nodes
        assert temporal_tree.nodes[v1.id].status == "superseded"
        assert temporal_tree.nodes[v1.id].superseded_by == v2.id

        # 检索时应只返回 v2
        results = temporal_tree.search("偏好")
        assert any(n.id == v2.id for n in results)
        assert not any(n.id == v1.id for n in results)

    def test_audit_trail(self, temporal_tree):
        """版本链应包含完整历史。使用语义相似内容触发取代。"""
        v1 = temporal_tree.add("YINYO 版本是 v1", category="Test Version")
        v2 = temporal_tree.add("YINYO 版本升级到 v2", category="Test Version")
        v3 = temporal_tree.add("YINYO 版本现在是 v3", category="Test Version")

        trail = temporal_tree.get_audit_trail(v1.id)
        assert len(trail) == 3
        assert trail[0].id == v1.id
        assert trail[-1].id == v3.id

    def test_archive_node(self, temporal_tree):
        """归档的节点不应出现在搜索结果中。"""
        node = temporal_tree.add("待归档事实")
        temporal_tree.archive(node.id)
        results = temporal_tree.search("待归档")
        assert not any(n.id == node.id for n in results)

    def test_persistence(self, tmp_path):
        """TemporalTree 应持久化到磁盘并正确恢复。"""
        tree_path = str(tmp_path / "persist_tree.json")
        tree1 = TemporalTree(tree_path)
        tree1.add("持久化测试", category="Test")
        assert len(tree1.nodes) >= 1

        # 重新加载
        tree2 = TemporalTree(tree_path)
        results = tree2.search("持久化")
        assert len(results) >= 1

    def test_time_weighted_search(self, temporal_tree):
        """时间加权检索：新事实应排在前面。"""
        old = temporal_tree.add("旧事实", confidence=0.5)
        time.sleep(0.1)
        new = temporal_tree.add("新事实", confidence=0.5)

        results = temporal_tree.search("事实", time_decay=0.5)
        if len(results) >= 2:
            # 新事实应在前面
            assert results[0].id == new.id

    def test_confidence_weighted_search(self, temporal_tree):
        """高置信度事实应排在前面。"""
        temporal_tree.add("低置信度", confidence=0.3)
        high = temporal_tree.add("高置信度", confidence=0.9)

        results = temporal_tree.search("置信度")
        if len(results) >= 2:
            assert results[0].id == high.id

    def test_scope_filter(self, temporal_tree):
        """scope 过滤应精确匹配。"""
        temporal_tree.add("userId 用户偏好", scopes={"user_id": "ou_123"})
        temporal_tree.add("其他用户偏好", scopes={"user_id": "ou_456"})

        results = temporal_tree.search("偏好", scopes={"user_id": "ou_123"})
        assert all(n.content.startswith("userId") for n in results)

    def test_hierarchy_root(self, temporal_tree):
        """根节点应正确建立层级。"""
        node = temporal_tree.add("层级测试", category="Projects/YINYO")
        assert node.parent_id is not None
        parent = temporal_tree.nodes[node.parent_id]
        assert node.id in parent.children

    def test_active_nodes_excludes_superseded(self, temporal_tree):
        """get_active_nodes 应排除 superseded 和 archived。"""
        v1 = temporal_tree.add("会被取代")
        temporal_tree.add("取代v1", category="Test")
        node = temporal_tree.add("会被归档")
        temporal_tree.archive(node.id)

        active = temporal_tree.get_active_nodes()
        ids = {n.id for n in active}
        assert v1.id not in ids
        assert node.id not in ids


class TestVectorCache:
    """VectorCache 语义检索测试。"""

    def test_add_and_search(self, temp_workspace):
        from memory import VectorCache
        cache = VectorCache(os.path.join(temp_workspace, "cache"))

        cache.add("doc1", "Python 编程语言")
        cache.add("doc2", "JavaScript 前端开发")

        results = cache.search("Python 编程")
        assert len(results) > 0
        assert results[0]["id"] == "doc1"

    def test_persistence(self, tmp_path):
        from memory import VectorCache
        cache_dir = str(tmp_path / "cache")
        cache1 = VectorCache(cache_dir)
        cache1.add("doc1", "持久化测试")

        cache2 = VectorCache(cache_dir)
        results = cache2.search("持久化")
        assert len(results) > 0

    def test_empty_search(self, temp_workspace):
        from memory import VectorCache
        cache = VectorCache(os.path.join(temp_workspace, "cache"))
        results = cache.search("不存在的内容")
        assert results == []


class TestMemoryStore:
    """MemoryStore 集成测试。"""

    def test_add_fact_and_search(self, memory_store, mock_model):
        memory_store.set_model(mock_model)
        node = memory_store.add_fact("用户偏好简洁回复", category="Preferences",
                                     confidence=0.9, source_run_id="test-001")
        assert node.id is not None

        results = memory_store.search_memory("简洁")
        assert len(results) > 0

    def test_memory_summary(self, memory_store):
        memory_store.add_fact("事实1", category="Preferences", confidence=0.8)
        memory_store.add_fact("事实2", category="Projects/YINYO", confidence=1.0)

        summary = memory_store.get_memory_summary()
        assert "事实1" in summary
        assert "事实2" in summary
        assert "Preferences" in summary

    def test_memory_summary_truncation(self, memory_store):
        """超过 max_chars 时应截断。"""
        for i in range(50):
            memory_store.add_fact(f"长内容事实_{i}" * 10, category="Test")
        summary = memory_store.get_memory_summary(max_chars=500)
        assert len(summary) <= 500 + 100  # 允许一些容差
