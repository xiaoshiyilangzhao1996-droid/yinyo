# YINYO v6.0 — 独立飞书 Agent 产品（认知层完整）
from .agent import YinyoAgent
from .model import ModelGateway, ThinkingMode
from .tools import Tool, ToolRegistry, tool, registry, load_yaml_tools, execute_tool_with_evidence, set_memory_workspace
from .evidence import EvidenceLedger, VerificationGate, RunManifest
from .governance import RiskPolicy, scan_secrets, redact_secrets
from .memory import MemoryStore, SimpleMemCompressor, VectorCache
from .evolution import SkillCrystallizer, ChangeManifest, SelfCheck, Skill, SkillStatus
from .session import SessionManager, Session
from .feishu_card import build_card_payload, build_text_payload, build_card_messages, is_card_invalid_error
from .feishu_format import optimize, split_long_message, strip_markdown_to_plain
from .memory_tool import memory_add, memory_replace, memory_remove, load_memory_context, ensure_memory_files

__version__ = "0.7.0"
__all__ = [
    "YinyoAgent", "ModelGateway", "ThinkingMode",
    "Tool", "ToolRegistry", "tool", "registry",
    "load_yaml_tools", "execute_tool_with_evidence", "set_memory_workspace",
    "EvidenceLedger", "VerificationGate", "RunManifest",
    "RiskPolicy", "scan_secrets", "redact_secrets",
    "MemoryStore", "SimpleMemCompressor", "VectorCache",
    "SkillCrystallizer", "ChangeManifest", "SelfCheck",
    "Skill", "SkillStatus",
    "SessionManager", "Session",
    "build_card_payload", "build_text_payload", "build_card_messages",
    "is_card_invalid_error",
    "optimize", "split_long_message", "strip_markdown_to_plain",
    "memory_add", "memory_replace", "memory_remove",
    "load_memory_context", "ensure_memory_files",
]
