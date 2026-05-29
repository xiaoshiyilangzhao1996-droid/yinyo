"""State handoff replay helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


HANDOFF_SCHEMA = "yinyo.handoff.v1"
HANDOFF_RESUME_SCHEMA = "yinyo.handoff_resume.v1"


def replay_handoff(path: str | Path, *, workspace: str | Path | None = None) -> dict[str, Any]:
    """Validate a handoff packet and build the resume context for the next run."""
    handoff_path = Path(path)
    root = Path(workspace).resolve() if workspace is not None else handoff_path.resolve().parents[2]
    try:
        handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return _resume_record(path=handoff_path, ok=False, blockers=[f"handoff_read_failed:{type(exc).__name__}"])

    checks = {
        "schema": handoff.get("schema") == HANDOFF_SCHEMA,
        "run_id": bool(handoff.get("run_id")),
        "intent": bool(handoff.get("intent", {}).get("original_task")),
        "constraints": _has_keys(handoff.get("constraints", {}), ["workspace", "max_steps", "max_runtime_seconds"]),
        "permissions": handoff.get("permissions", {}).get("confirm_tools_require_structured_metadata") is True,
        "artifacts": _has_keys(handoff.get("artifacts", {}), ["evidence_file", "manifest_file"]),
        "provenance": isinstance(handoff.get("provenance", {}).get("source_audit"), dict),
        "budget_state": _has_keys(handoff.get("budget_state", {}), ["max_steps", "steps_used", "steps_remaining", "max_runtime_seconds", "model_usage"]),
        "trace_history": _has_keys(handoff.get("trace_history", {}), ["correlation_id", "evidence_hashes", "tools_used", "model_errors"]),
        "risk": isinstance(handoff.get("risk", {}).get("risk_notes", []), list),
        "unresolved": isinstance(handoff.get("unresolved", []), list),
    }
    artifacts = handoff.get("artifacts", {}) if isinstance(handoff.get("artifacts"), dict) else {}
    evidence_path = _resolve_artifact(root, artifacts.get("evidence_file", ""))
    manifest_path = _resolve_artifact(root, artifacts.get("manifest_file", ""))
    checks["evidence_artifact"] = bool(artifacts.get("evidence_file"))
    checks["manifest_artifact"] = bool(artifacts.get("manifest_file"))
    artifact_exists = {
        "evidence_file": evidence_path.is_file(),
        "manifest_file": manifest_path.is_file(),
    }
    checks["evidence_artifact_exists"] = artifact_exists["evidence_file"]
    checks["manifest_artifact_exists"] = artifact_exists["manifest_file"]
    checks["budget_recoverable"] = _budget_recoverable(handoff.get("budget_state", {}))
    checks["trace_recoverable"] = _trace_recoverable(
        handoff.get("trace_history", {}),
        correlation_id=str(handoff.get("correlation_id", "")),
    )

    blockers = [name for name, passed in checks.items() if not passed]
    resume_context = {
        "run_id": handoff.get("run_id", ""),
        "correlation_id": handoff.get("correlation_id", ""),
        "original_task": handoff.get("intent", {}).get("original_task", ""),
        "final_status": handoff.get("intent", {}).get("final_status", ""),
        "constraints": handoff.get("constraints", {}),
        "permissions": handoff.get("permissions", {}),
        "artifacts": {
            "evidence_file": str(evidence_path),
            "manifest_file": str(manifest_path),
            "change_manifest_file": str(_resolve_artifact(root, artifacts.get("change_manifest_file", ""))),
            "exists": artifact_exists,
        },
        "provenance": handoff.get("provenance", {}),
        "budget_state": handoff.get("budget_state", {}),
        "trace_history": handoff.get("trace_history", {}),
        "risk": handoff.get("risk", {}),
        "unresolved": handoff.get("unresolved", []),
    }
    inherited = {
        "intent": handoff.get("intent", {}),
        "constraints": handoff.get("constraints", {}),
        "permissions": handoff.get("permissions", {}),
        "artifacts": resume_context["artifacts"],
        "provenance": handoff.get("provenance", {}),
        "budget_state": handoff.get("budget_state", {}),
        "trace_history": handoff.get("trace_history", {}),
        "risk": handoff.get("risk", {}),
        "unresolved": handoff.get("unresolved", []),
    }
    return _resume_record(
        path=handoff_path,
        ok=not blockers,
        blockers=blockers,
        checks=checks,
        resume_context=resume_context,
        inherited=inherited,
        run_id=str(handoff.get("run_id", "")),
        source_schema=str(handoff.get("schema", "")),
    )


def _resume_record(
    *,
    path: Path,
    ok: bool,
    blockers: list[str],
    checks: dict[str, bool] | None = None,
    resume_context: dict[str, Any] | None = None,
    inherited: dict[str, Any] | None = None,
    run_id: str = "",
    source_schema: str = "",
) -> dict[str, Any]:
    return {
        "schema": HANDOFF_RESUME_SCHEMA,
        "run_id": run_id,
        "source_schema": source_schema,
        "handoff_path": str(path),
        "source_path": str(path),
        "resume_ready": ok,
        "ok": ok,
        "checks": checks or {},
        "blockers": blockers,
        "inherited": inherited or {},
        "resume_context": resume_context or {},
    }


def _has_keys(value: Any, keys: list[str]) -> bool:
    return isinstance(value, dict) and all(key in value for key in keys)


def _budget_recoverable(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    max_steps = value.get("max_steps")
    steps_used = value.get("steps_used")
    steps_remaining = value.get("steps_remaining")
    max_runtime_seconds = value.get("max_runtime_seconds")
    model_usage = value.get("model_usage")
    return (
        isinstance(max_steps, int)
        and isinstance(steps_used, int)
        and isinstance(steps_remaining, int)
        and max_steps >= 0
        and steps_used >= 0
        and steps_remaining >= 0
        and steps_used + steps_remaining == max_steps
        and isinstance(max_runtime_seconds, (int, float))
        and max_runtime_seconds > 0
        and isinstance(model_usage, dict)
    )


def _trace_recoverable(value: Any, *, correlation_id: str) -> bool:
    if not isinstance(value, dict):
        return False
    trace_correlation_id = value.get("correlation_id")
    return (
        bool(correlation_id)
        and trace_correlation_id == correlation_id
        and isinstance(value.get("evidence_hashes"), list)
        and isinstance(value.get("tools_used"), list)
        and isinstance(value.get("model_errors"), list)
    )


def _resolve_artifact(root: Path, value: Any) -> Path:
    text = str(value or "")
    if not text:
        return root / "__missing__"
    path = Path(text)
    if path.is_absolute():
        return path
    return root / path
