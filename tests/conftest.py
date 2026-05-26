# conftest.py — YINYO test fixtures (对标 Hermes pytest convention)
"""共享测试夹具。提供 mock agent、mock model、临时 workspace。"""

import pytest, sys, os, shutil, tempfile, json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'yinyo'))

from model import ModelGateway, ThinkingMode
from memory import MemoryStore, TemporalTree
from tools import ToolRegistry, tool
from evidence import EvidenceLedger, VerificationGate, RunManifest
from governance import RiskPolicy


# ═══════════════════════════════════════════════════════
# Mock Model
# ═══════════════════════════════════════════════════════

@pytest.fixture
def mock_model():
    """返回一个 mock ModelGateway，可编程响应。"""
    model = ModelGateway(api_key="")  # 无 API key → mock 模式
    return model


@pytest.fixture
def mock_agent(mock_model, tmp_path):
    """返回一个配置好 mock model 的 YinyoAgent。"""
    from agent import YinyoAgent
    ws = str(tmp_path)
    agent = YinyoAgent(workspace=ws, max_steps=10)
    agent.model = mock_model
    # 禁用 deep-reflect（避免干扰测试）
    agent.run_count = 999  # 不会触发 deep-reflect
    return agent


# ═══════════════════════════════════════════════════════
# Temporary Workspace
# ═══════════════════════════════════════════════════════

@pytest.fixture
def temp_workspace(tmp_path):
    """临时 workspace 目录。"""
    ws = str(tmp_path / "test_ws")
    os.makedirs(ws, exist_ok=True)
    return ws


# ═══════════════════════════════════════════════════════
# TemporalTree
# ═══════════════════════════════════════════════════════

@pytest.fixture
def temporal_tree(tmp_path):
    """空的 TemporalTree 实例。"""
    tree_path = str(tmp_path / "test_tree.json")
    return TemporalTree(tree_path)


# ═══════════════════════════════════════════════════════
# Memory Store
# ═══════════════════════════════════════════════════════

@pytest.fixture
def memory_store(tmp_path):
    """空的 MemoryStore 实例。"""
    ws = str(tmp_path / "test_ws")
    os.makedirs(ws, exist_ok=True)
    return MemoryStore(ws)


# ═══════════════════════════════════════════════════════
# Tool Registry
# ═══════════════════════════════════════════════════════

@pytest.fixture
def tool_registry():
    """返回预注册了内置工具的 ToolRegistry。"""
    try:
        from tools import registry
        return registry
    except Exception:
        return ToolRegistry()


# ═══════════════════════════════════════════════════════
# Helper: 创建测试文件
# ═══════════════════════════════════════════════════════

def create_test_file(path: str, content: str):
    """在指定路径创建测试文件。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
