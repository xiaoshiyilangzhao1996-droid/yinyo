"""Runtime configuration for deployable YINYO services."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Raised when runtime configuration is invalid."""


@dataclass
class RuntimeConfig:
    profile: str = "local"
    transport: str = "ws"
    workspace: str = "."
    host: str = "0.0.0.0"
    port: int = 8080
    app_id: str = ""
    app_secret: str = ""
    verify_token: str = ""
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    default_model: str = "deepseek-v4-flash"
    model_timeout_seconds: int = 120
    model_retry_count: int = 0
    model_retry_backoff_seconds: float = 0
    ack_deadline_seconds: float = 3.0
    max_steps: int = 50
    job_max_workers: int = 4
    event_store_path: str = ""
    job_store_path: str = ""
    log_path: str = ""
    smoke_evidence_path: str = ""
    runtime_lock_path: str = ""
    smoke_mode: bool = False
    ws_sdk_session_id: str = ""

    @classmethod
    def load(cls, config_path: str | None = None, **overrides: Any) -> "RuntimeConfig":
        data: dict[str, Any] = {}
        if config_path:
            path = Path(config_path)
            if not path.is_file():
                raise ConfigError(f"Config file not found: {config_path}")
            data.update(_load_mapping(path))

        env_map = {
            "profile": "YINYO_PROFILE",
            "transport": "YINYO_TRANSPORT",
            "workspace": "YINYO_WORKSPACE",
            "host": "YINYO_HOST",
            "port": "YINYO_PORT",
            "app_id": "FEISHU_APP_ID",
            "app_secret": "FEISHU_APP_SECRET",
            "verify_token": "FEISHU_VERIFY_TOKEN",
            "deepseek_api_key": "DEEPSEEK_API_KEY",
            "deepseek_base_url": "DEEPSEEK_BASE_URL",
            "default_model": "YINYO_MODEL",
            "model_timeout_seconds": "YINYO_MODEL_TIMEOUT_SECONDS",
            "model_retry_count": "YINYO_MODEL_RETRY_COUNT",
            "model_retry_backoff_seconds": "YINYO_MODEL_RETRY_BACKOFF_SECONDS",
            "ack_deadline_seconds": "YINYO_ACK_DEADLINE_SECONDS",
            "max_steps": "YINYO_MAX_STEPS",
            "job_max_workers": "YINYO_JOB_MAX_WORKERS",
            "event_store_path": "YINYO_EVENT_STORE",
            "job_store_path": "YINYO_JOB_STORE",
            "log_path": "YINYO_LOG_PATH",
            "smoke_evidence_path": "YINYO_SMOKE_EVIDENCE",
            "runtime_lock_path": "YINYO_RUNTIME_LOCK",
            "smoke_mode": "YINYO_SMOKE_MODE",
            "ws_sdk_session_id": "YINYO_WS_SDK_SESSION_ID",
        }
        for key, env_key in env_map.items():
            value = os.environ.get(env_key)
            if value not in (None, ""):
                data[key] = value

        for key, value in overrides.items():
            if value not in (None, ""):
                data[key] = value

        cfg = cls(**_coerce(data))
        cfg.apply_defaults()
        return cfg

    def apply_defaults(self) -> None:
        self.profile = (self.profile or "local").strip().lower()
        self.transport = (self.transport or "ws").strip().lower()
        self.workspace = os.path.abspath(self.workspace or ".")
        if self.profile == "local":
            self.host = self.host or "127.0.0.1"
            self.model_retry_count = self.model_retry_count or 0
            self.model_retry_backoff_seconds = self.model_retry_backoff_seconds or 0
        elif self.profile == "staging":
            self.model_retry_count = self.model_retry_count or 1
            self.model_retry_backoff_seconds = self.model_retry_backoff_seconds or 0.5
        elif self.profile == "production":
            self.model_retry_count = self.model_retry_count or 2
            self.model_retry_backoff_seconds = self.model_retry_backoff_seconds or 1.0
        self.event_store_path = self.event_store_path or os.path.join(self.workspace, "gateway_events.jsonl")
        self.job_store_path = self.job_store_path or os.path.join(self.workspace, "runtime_jobs.jsonl")
        self.log_path = self.log_path or os.path.join(self.workspace, "runtime.jsonl")
        self.smoke_evidence_path = self.smoke_evidence_path or os.path.join(self.workspace, "smoke_evidence.jsonl")
        self.runtime_lock_path = self.runtime_lock_path or os.path.join(self.workspace, "yinyo_runtime.lock")

    def validate(self, *, require_secrets: bool = True) -> None:
        missing = []
        if not self.workspace:
            missing.append("workspace")
        if self.profile not in {"local", "staging", "production"}:
            raise ConfigError("profile must be one of: local, staging, production")
        if self.transport not in {"ws", "http"}:
            raise ConfigError("transport must be one of: ws, http")
        if require_secrets:
            required_secret_fields = ["app_id", "app_secret", "deepseek_api_key"]
            if self.transport == "http":
                required_secret_fields.append("verify_token")
            for field in required_secret_fields:
                if not getattr(self, field):
                    missing.append(field)
        if missing:
            names = ", ".join(missing)
            raise ConfigError(f"Missing required runtime config: {names}")
        if require_secrets:
            placeholders = [
                field
                for field in required_secret_fields
                if _looks_like_placeholder(getattr(self, field, ""))
            ]
            if placeholders:
                names = ", ".join(placeholders)
                raise ConfigError(f"Placeholder runtime config values are not allowed for live smoke: {names}")
        if int(self.port) <= 0 or int(self.port) > 65535:
            raise ConfigError("port must be between 1 and 65535")
        if int(self.max_steps) <= 0:
            raise ConfigError("max_steps must be positive")
        if int(self.job_max_workers) <= 0:
            raise ConfigError("job_max_workers must be positive")
        if int(self.model_timeout_seconds) <= 0:
            raise ConfigError("model_timeout_seconds must be positive")
        if int(self.model_retry_count) < 0:
            raise ConfigError("model_retry_count must be zero or positive")
        if float(self.model_retry_backoff_seconds) < 0:
            raise ConfigError("model_retry_backoff_seconds must be zero or positive")
        if float(self.ack_deadline_seconds) <= 0:
            raise ConfigError("ack_deadline_seconds must be positive")
        if self.transport == "ws" and float(self.ack_deadline_seconds) > 3:
            raise ConfigError("ws transport requires ack_deadline_seconds <= 3")
        if self.profile == "production":
            if self.smoke_mode:
                raise ConfigError("production profile must not enable smoke_mode")
            if self.host in {"127.0.0.1", "localhost"}:
                raise ConfigError("production profile must not bind only to localhost")
            if int(self.model_timeout_seconds) < 30:
                raise ConfigError("production profile requires model_timeout_seconds >= 30")
            if int(self.model_retry_count) < 1:
                raise ConfigError("production profile requires model_retry_count >= 1")

    def feishu_config(self) -> dict[str, Any]:
        return {
            "app_id": self.app_id,
            "app_secret": self.app_secret,
            "verify_token": self.verify_token,
            "smoke_mode": self.smoke_mode,
        }


def _load_mapping(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        loaded = json.loads(text)
        if not isinstance(loaded, dict):
            raise ConfigError("Config JSON must be an object")
        return loaded

    data: dict[str, Any] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            raise ConfigError(f"Invalid config line: {line}")
        key, value = stripped.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def _coerce(data: dict[str, Any]) -> dict[str, Any]:
    result = dict(data)
    for key in ("port", "max_steps", "job_max_workers", "model_timeout_seconds", "model_retry_count"):
        if key in result:
            try:
                result[key] = int(result[key])
            except (TypeError, ValueError) as exc:
                raise ConfigError(f"{key} must be an integer") from exc
    for key in ("model_retry_backoff_seconds", "ack_deadline_seconds"):
        if key not in result:
            continue
        try:
            result[key] = float(result[key])
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"{key} must be a number") from exc
    for key in ("smoke_mode",):
        if key in result:
            result[key] = _coerce_bool(result[key], key)
    return result


def _coerce_bool(value: Any, key: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return True
        if lowered in {"0", "false", "no", "n", "off"}:
            return False
    raise ConfigError(f"{key} must be a boolean")


def _looks_like_placeholder(value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    lowered = text.lower()
    if lowered.startswith("<") and lowered.endswith(">"):
        return True
    placeholder_tokens = {
        "placeholder",
        "example",
        "fake",
        "fixture",
        "mock",
        "none",
        "null",
        "redacted",
        "sample",
        "synthetic",
        "todo",
        "xxx",
    }
    parts = [part for part in lowered.replace("_", "-").split("-") if part]
    return any(part in placeholder_tokens for part in parts)


def redact_config(cfg: RuntimeConfig) -> dict[str, Any]:
    data = dict(cfg.__dict__)
    for key in ("app_secret", "verify_token", "deepseek_api_key"):
        if data.get(key):
            data[key] = "***"
    return data


def build_config_template(*, live_smoke: bool = False, workspace: str = "./workspace") -> str:
    smoke_mode = "true" if live_smoke else "false"
    secret_suffix = "_secret"
    api_key_suffix = "_api_key"
    token_suffix = "_token"
    lines = [
        "# YINYO runtime config. Keep this file outside git.",
        "# Put raw secrets only in this local file or environment variables.",
        "# If any credential was pasted into chat, logs, or a ticket, rotate it before release.",
        f"workspace={workspace}",
        "profile=local",
        "transport=ws",
        "host=0.0.0.0",
        "port=8080",
        "",
        "# Feishu self-built app credentials.",
        "app_id=",
        f"app{secret_suffix}=",
        "# Required only for HTTP webhook callbacks; optional for ws long connection.",
        f"verify{token_suffix}=",
        "",
        "# DeepSeek model access.",
        f"deepseek{api_key_suffix}=",
        "deepseek_base_url=https://api.deepseek.com",
        "default_model=deepseek-v4-flash",
        "model_timeout_seconds=120",
        "model_retry_count=1",
        "model_retry_backoff_seconds=0.5",
        "",
        "# Feishu long-connection ACK must stay <= 3 seconds.",
        "ack_deadline_seconds=3",
        "# Optional live provenance marker. Smoke bundle inherits this value; --ws-sdk-session-id must match if provided.",
        "ws_sdk_session_id=",
        "max_steps=50",
        "# Bounded async Feishu job workers; saturated queues return queue_saturated.",
        "job_max_workers=4",
        "",
        "# Runtime evidence stores.",
        f"event_store_path={workspace}/gateway_events.jsonl",
        f"job_store_path={workspace}/runtime_jobs.jsonl",
        f"log_path={workspace}/runtime.jsonl",
        f"smoke_evidence_path={workspace}/smoke_evidence.jsonl",
        f"runtime_lock_path={workspace}/yinyo_runtime.lock",
        "",
        "# Enable only while collecting the deterministic card_fallback live smoke probe.",
        f"smoke_mode={smoke_mode}",
    ]
    if live_smoke:
        lines.extend([
            "",
            "# Live smoke sequence:",
            "# 1. Run: yinyo serve --config ./yinyo.env --dry-run",
            "# 2. Run: yinyo smoke preflight --config ./yinyo.env",
            "# 3. Run: yinyo smoke reset --config ./yinyo.env --confirm-reset",
            "# 4. Start and keep running: yinyo serve --config ./yinyo.env",
            "# 5. Perform real Feishu text, image, duplicate, and /yinyo-smoke card-fallback actions.",
            "# 6. Record advanced evidence with: yinyo smoke record-advanced --config ./yinyo.env --scenario <scenario> ...",
            "# 7. Run in another terminal: yinyo smoke wait --config ./yinyo.env",
            "# 8. If wait times out, run: yinyo smoke status --config ./yinyo.env --json",
            "# 9. Set smoke_mode=false, restart yinyo serve, and confirm: yinyo smoke status --config ./yinyo.env --json",
            "# 10. Bundle: yinyo smoke bundle --config ./yinyo.env --output ./workspace/smoke-bundle --handoff-dir ./workspace/runs --live-attestation-id <attestation-id> --tenant-hash <sha256-tenant>",
            "# 11. Verify: python scripts/verify_release.py --target 1.0.0 --bundle ./workspace/smoke-bundle --candidate 1.0.0",
        ])
    return "\n".join(lines) + "\n"
