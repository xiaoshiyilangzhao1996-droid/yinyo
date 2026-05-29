"""Service assembly for deployable YINYO runtime."""

from __future__ import annotations

from .agent import YinyoAgent
from .config import RuntimeConfig
from .event_store import JsonlEventStore
from .feishu_adapter import FeishuAdapter
from .jobs import JsonlJobQueue
from .runtime_log import RuntimeLogger
from .runtime_lock import RuntimeStoreLock
from .smoke import SmokeEvidenceRecorder
from .feishu_ws import FeishuLongConnectionTransport


def _startup_log_fields(config: RuntimeConfig) -> dict:
    """Return the non-secret runtime surface needed to audit a live service."""
    return {
        "profile": config.profile,
        "transport": config.transport,
        "host": config.host,
        "port": config.port,
        "workspace": config.workspace,
        "default_model": config.default_model,
        "model_timeout_seconds": config.model_timeout_seconds,
        "model_retry_count": config.model_retry_count,
        "model_retry_backoff_seconds": config.model_retry_backoff_seconds,
        "ack_deadline_seconds": config.ack_deadline_seconds,
        "max_steps": config.max_steps,
        "job_max_workers": config.job_max_workers,
        "smoke_mode": config.smoke_mode,
        "event_store_path": config.event_store_path,
        "job_store_path": config.job_store_path,
        "log_path": config.log_path,
        "smoke_evidence_path": config.smoke_evidence_path,
        "runtime_lock_path": config.runtime_lock_path,
        "ws_sdk_session_id": config.ws_sdk_session_id,
    }


def build_service(config: RuntimeConfig) -> FeishuAdapter:
    config.validate(require_secrets=True)
    agent = YinyoAgent(
        workspace=config.workspace,
        max_steps=config.max_steps,
        api_key=config.deepseek_api_key,
        base_url=config.deepseek_base_url,
        default_model=config.default_model,
        model_timeout_seconds=config.model_timeout_seconds,
        model_retry_count=config.model_retry_count,
        model_retry_backoff_seconds=config.model_retry_backoff_seconds,
    )
    adapter = FeishuAdapter(agent=agent, config=config.feishu_config())
    adapter.gateway.queue = JsonlJobQueue(config.job_store_path, max_workers=config.job_max_workers)
    adapter.gateway.event_store = JsonlEventStore(config.event_store_path)
    adapter.gateway.logger = RuntimeLogger(config.log_path)
    adapter.gateway.smoke_recorder = SmokeEvidenceRecorder(config.smoke_evidence_path)
    return adapter


def serve(config: RuntimeConfig) -> None:
    with RuntimeStoreLock(config.runtime_lock_path):
        adapter = build_service(config)
        adapter.gateway.logger.record(
            "service_start",
            correlation_id="service",
            **_startup_log_fields(config),
        )
        try:
            if config.transport == "ws":
                transport = FeishuLongConnectionTransport(
                    adapter=adapter,
                    app_id=config.app_id,
                    app_secret=config.app_secret,
                    logger=adapter.gateway.logger,
                    ack_deadline_seconds=config.ack_deadline_seconds,
                    ws_sdk_session_id=config.ws_sdk_session_id,
                )
                transport.start()
            else:
                adapter.start_server(host=config.host, port=config.port)
        except Exception as exc:
            adapter.gateway.logger.record(
                "service_stop",
                correlation_id="service",
                status="failed",
                error_type=exc.__class__.__name__,
                transport=config.transport,
            )
            raise
        else:
            adapter.gateway.logger.record(
                "service_stop",
                correlation_id="service",
                status="stopped",
                transport=config.transport,
            )
