"""Local preflight checks before live Feishu smoke."""

from __future__ import annotations

import importlib.util
import importlib
import os
import tempfile
from dataclasses import dataclass
from typing import Any

from .config import ConfigError, RuntimeConfig
from .runtime_lock import check_runtime_store_lock_available
from .smoke import verify_live_provenance


@dataclass
class PreflightCheck:
    name: str
    ok: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "detail": self.detail}


def run_preflight(config: RuntimeConfig, *, allow_existing_evidence: bool = False) -> dict[str, Any]:
    """Run local, non-network checks for a live smoke attempt."""

    checks: list[PreflightCheck] = [
        _validate_config(config),
        _check_workspace_writable(config.workspace),
        _check_parent_writable(config.event_store_path, "event_store_path"),
        _check_parent_writable(config.job_store_path, "job_store_path"),
        _check_parent_writable(config.log_path, "log_path"),
        _check_parent_writable(config.smoke_evidence_path, "smoke_evidence_path"),
        _check_fresh_evidence_files(config, allow_existing=allow_existing_evidence),
        _check_runtime_lock(config),
        _check_ws_sdk(config),
        _check_ws_session_provenance(config),
        _check_ack_deadline(config),
        _check_smoke_mode(config),
    ]
    return {
        "ok": all(item.ok for item in checks),
        "profile": config.profile,
        "transport": config.transport,
        "workspace": config.workspace,
        "smoke_evidence_path": config.smoke_evidence_path,
        "allow_existing_evidence": allow_existing_evidence,
        "checks": [item.to_dict() for item in checks],
    }


def format_preflight(result: dict[str, Any]) -> str:
    status = "OK" if result.get("ok") else "ATTENTION"
    lines = [
        f"YINYO live smoke preflight: {status}",
        f"profile: {result.get('profile', '')}",
        f"transport: {result.get('transport', '')}",
        f"workspace: {result.get('workspace', '')}",
        f"smoke_evidence_path: {result.get('smoke_evidence_path', '')}",
        "note: enable smoke_mode only while collecting the live card_fallback probe.",
        "checks:",
    ]
    for item in result.get("checks", []):
        marker = "OK" if item.get("ok") else "FAIL"
        detail = f" - {item.get('detail', '')}" if item.get("detail") else ""
        lines.append(f"- {marker} {item.get('name', '')}{detail}")
    return "\n".join(lines)


def _validate_config(config: RuntimeConfig) -> PreflightCheck:
    try:
        config.validate(require_secrets=True)
    except ConfigError as exc:
        detail = (
            f"{exc}. Fill missing values in the local config file or environment variables; "
            "do not paste raw secrets into chat. Rotate any credential that was exposed before release."
        )
        return PreflightCheck("runtime_config", False, detail)
    return PreflightCheck("runtime_config", True)


def _check_workspace_writable(path: str) -> PreflightCheck:
    try:
        os.makedirs(path, exist_ok=True)
        _write_probe(path)
    except Exception as exc:
        return PreflightCheck("workspace_writable", False, str(exc))
    return PreflightCheck("workspace_writable", True)


def _check_parent_writable(path: str, name: str) -> PreflightCheck:
    parent = os.path.dirname(os.path.abspath(path)) or "."
    try:
        os.makedirs(parent, exist_ok=True)
        _write_probe(parent)
    except Exception as exc:
        return PreflightCheck(name, False, str(exc))
    return PreflightCheck(name, True, path)


def _check_fresh_evidence_files(config: RuntimeConfig, *, allow_existing: bool = False) -> PreflightCheck:
    paths = {
        "smoke_evidence": config.smoke_evidence_path,
        "runtime_log": config.log_path,
        "job_store": config.job_store_path,
        "event_store": config.event_store_path,
    }
    existing = [
        f"{name}:{path}"
        for name, path in paths.items()
        if _file_has_content(path)
    ]
    if not existing:
        return PreflightCheck("fresh_evidence_files", True, "no existing evidence records")
    detail = (
        "existing evidence records found; run "
        "yinyo smoke reset --config <config> --confirm-reset before a fresh 1.0 live smoke attempt: "
        + ", ".join(existing)
    )
    if allow_existing:
        return PreflightCheck("fresh_evidence_files", True, "allowed existing evidence records: " + ", ".join(existing))
    return PreflightCheck("fresh_evidence_files", False, detail)


def _file_has_content(path: str) -> bool:
    try:
        return os.path.isfile(path) and os.path.getsize(path) > 0
    except OSError:
        return False


def _check_ws_sdk(config: RuntimeConfig) -> PreflightCheck:
    if config.transport != "ws":
        return PreflightCheck("lark_oapi_sdk", True, "not required for http transport")
    if importlib.util.find_spec("lark_oapi") is None:
        return PreflightCheck("lark_oapi_sdk", False, "lark-oapi is required for ws transport")
    try:
        lark = importlib.import_module("lark_oapi")
        _validate_lark_oapi_contract(lark)
    except Exception as exc:
        return PreflightCheck("lark_oapi_sdk", False, f"lark-oapi SDK contract invalid: {exc}")
    return PreflightCheck("lark_oapi_sdk", True, "long-connection SDK contract available")


def _check_ws_session_provenance(config: RuntimeConfig) -> PreflightCheck:
    if config.transport != "ws":
        return PreflightCheck("ws_sdk_session_id", True, "not required for http transport")
    session_id = str(config.ws_sdk_session_id or "").strip()
    manifest = {
        "runtime": {"transport": config.transport},
        "live_provenance": {
            "schema": "yinyo.live_provenance.v1",
            "operator_attestation_id": "preflight-attestation",
            "feishu_app_id_hash": "a" * 64,
            "tenant_hash": "b" * 64,
            "ws_sdk_session_id": session_id,
        },
    }
    blockers = verify_live_provenance(manifest, require_complete=True, prefix="preflight")
    if blockers:
        return PreflightCheck(
            "ws_sdk_session_id",
            False,
            "; ".join(blockers)
            + ". Set ws_sdk_session_id in the same config used by smoke bundle; if --ws-sdk-session-id is provided, it must match.",
        )
    return PreflightCheck(
        "ws_sdk_session_id",
        True,
        "will be written to service_start/ws_transport_start and inherited by smoke bundle; --ws-sdk-session-id must match if provided",
    )


def _validate_lark_oapi_contract(lark: Any) -> None:
    dispatcher = getattr(lark, "EventDispatcherHandler", None)
    builder_factory = getattr(dispatcher, "builder", None)
    if not callable(builder_factory):
        raise RuntimeError("EventDispatcherHandler.builder missing")
    builder = builder_factory("", "")
    if not callable(getattr(builder, "register_p2_im_message_receive_v1", None)):
        raise RuntimeError("register_p2_im_message_receive_v1 missing")
    if not callable(getattr(builder, "build", None)):
        raise RuntimeError("EventDispatcherHandler builder.build missing")
    ws = getattr(lark, "ws", None)
    if not callable(getattr(ws, "Client", None)):
        raise RuntimeError("ws.Client missing")


def _check_ack_deadline(config: RuntimeConfig) -> PreflightCheck:
    deadline = float(config.ack_deadline_seconds)
    if config.transport == "ws" and deadline > 3:
        return PreflightCheck("ack_deadline", False, "ws transport must ack within 3 seconds")
    return PreflightCheck("ack_deadline", True, f"{deadline}s")


def _check_smoke_mode(config: RuntimeConfig) -> PreflightCheck:
    if config.smoke_mode:
        return PreflightCheck(
            "smoke_mode",
            True,
            "enabled; send /yinyo-smoke card-fallback during smoke and disable afterward",
        )
    return PreflightCheck(
        "smoke_mode",
        True,
        "disabled; enable only for deterministic card_fallback evidence",
    )


def _check_runtime_lock(config: RuntimeConfig) -> PreflightCheck:
    ok, detail = check_runtime_store_lock_available(config.runtime_lock_path)
    return PreflightCheck("runtime_store_lock", ok, detail)


def _write_probe(directory: str) -> None:
    fd, path = tempfile.mkstemp(prefix=".yinyo-preflight-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("ok")
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
