# YINYO v8.1 — 独立飞书 Agent 产品（Dual-Process 记忆 + Provider Chain + Trace2Skill）
from .agent import YinyoAgent
from .model import ModelGateway, ThinkingMode
from .tools import Tool, ToolRegistry, tool, registry, load_yaml_tools, execute_tool_with_evidence, set_memory_workspace
from .evidence import EvidenceLedger, VerificationGate, RunManifest
from .governance import RiskPolicy, scan_secrets, redact_secrets
from .memory import MemoryStore, SimpleMemCompressor, VectorCache, TemporalTree, FactExtractor
from .evolution import SkillCrystallizer, ChangeManifest, SelfCheck, Skill, SkillStatus, SkillEvolution
from .session import SessionManager, Session
from .feishu_card import build_card_payload, build_text_payload, build_card_messages, is_card_invalid_error
from .feishu_format import optimize, split_long_message, strip_markdown_to_plain
from .memory_tool import memory_add, memory_replace, memory_remove, load_memory_context, ensure_memory_files
from .vision_adapter import VisionAdapter, get_vision_adapter
from .delegate import SubAgent, DelegateResult

__version__ = "0.8.1"
__all__ = [
    "YinyoAgent", "ModelGateway", "ThinkingMode",
    "Tool", "ToolRegistry", "tool", "registry",
    "load_yaml_tools", "execute_tool_with_evidence", "set_memory_workspace",
    "EvidenceLedger", "VerificationGate", "RunManifest",
    "RiskPolicy", "scan_secrets", "redact_secrets",
    "MemoryStore", "SimpleMemCompressor", "VectorCache",
    "TemporalTree", "FactExtractor",
    "SkillCrystallizer", "ChangeManifest", "SelfCheck",
    "Skill", "SkillStatus", "SkillEvolution",
    "SessionManager", "Session",
    "build_card_payload", "build_text_payload", "build_card_messages",
    "is_card_invalid_error",
    "optimize", "split_long_message", "strip_markdown_to_plain",
    "memory_add", "memory_replace", "memory_remove",
    "load_memory_context", "ensure_memory_files",
    "VisionAdapter", "get_vision_adapter",
    "SubAgent", "DelegateResult",
]
