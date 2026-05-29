"""Runtime diagnostics for deployable YINYO services."""

from __future__ import annotations

import json
import os
import time
from collections import Counter
from typing import Any

from .runtime_lock import check_runtime_store_lock_available
from .smoke import required_live_smoke_scenarios, verify_correlation_chains, verify_smoke_evidence

TRACE_FAILURE_DIAGNOSIS_SCHEMA = "yinyo.trace_failure_diagnosis.v1"


def summarize_runtime(
    *,
    log_path: str,
    job_store_path: str,
    smoke_evidence_path: str,
    event_store_path: str = "",
    runtime_lock_path: str = "",
    transport: str = "",
) -> dict[str, Any]:
    """Build an operator-facing health summary from local JSONL runtime files."""

    logs = _read_jsonl(log_path)
    jobs = _read_jsonl(job_store_path)
    events = _read_jsonl(event_store_path) if event_store_path else []
    event_counts = Counter(str(item.get("event", "")) for item in logs if item.get("event"))
    event_keys = [str(item.get("event_key", "")) for item in events if item.get("event_key")]
    latest_jobs = _latest_jobs(jobs)
    job_status_counts = Counter(str(job.get("status", "")) for job in latest_jobs.values() if job.get("status"))
    failed_jobs = [job for job in latest_jobs.values() if job.get("status") == "failed"]
    outbox_failures = [
        item for item in logs
        if item.get("event") == "outbox_delivery" and item.get("success") is False
    ]
    outbox_dead_letters = [item for item in outbox_failures if item.get("dead_letter") is True]
    ack_deadline_misses = [
        item for item in logs
        if item.get("event") == "ws_event_received" and item.get("ack_within_deadline") is False
    ]
    ws_event_records = [item for item in logs if item.get("event") == "ws_event_received"]
    rejected = [item for item in logs if item.get("event") == "webhook_rejected"]
    runtime_lock = _runtime_lock_summary(runtime_lock_path)
    service = _service_summary(logs)
    smoke_transport = transport or str(service.get("transport", ""))
    smoke = verify_smoke_evidence(smoke_evidence_path, required=set(required_live_smoke_scenarios(smoke_transport)))
    correlation = verify_correlation_chains(
        smoke_records=_read_jsonl(smoke_evidence_path),
        logs=logs,
        jobs=jobs,
        events=events,
        required=set(required_live_smoke_scenarios(smoke_transport)),
        transport=smoke_transport,
    )
    alerts = _build_alerts(
        logs,
        latest_jobs,
        smoke,
        outbox_failures,
        outbox_dead_letters,
        rejected,
        ack_deadline_misses,
        event_store_path,
        event_keys,
        runtime_lock,
        service,
        correlation,
    )
    diagnosis = build_trace_failure_diagnosis(
        logs=logs,
        jobs=latest_jobs,
        events=events,
        smoke=smoke,
        correlation=correlation,
        runtime_lock=runtime_lock,
        service=service,
        alerts=alerts,
    )

    return {
        "ok": not alerts,
        "generated_at": time.time(),
        "paths": {
            "runtime_log": log_path,
            "job_store": job_store_path,
            "smoke_evidence": smoke_evidence_path,
            "event_store": event_store_path,
            "runtime_lock": runtime_lock_path,
        },
        "runtime": {
            "records": len(logs),
            "event_counts": dict(sorted(event_counts.items())),
            "last_correlation_id": _last_value(logs, "correlation_id"),
            "ws": _ws_summary(ws_event_records),
            "service": service,
        },
        "jobs": {
            "records": len(jobs),
            "latest": len(latest_jobs),
            "status_counts": dict(sorted(job_status_counts.items())),
            "failed": [_job_brief(job) for job in failed_jobs[-5:]],
        },
        "event_store": {
            "records": len(events),
            "unique_event_keys": len(set(event_keys)),
            "last_event_key": event_keys[-1] if event_keys else "",
        },
        "runtime_lock": runtime_lock,
        "smoke": smoke,
        "correlation": correlation,
        "failures": {
            "webhook_rejected": [_log_brief(item) for item in rejected[-5:]],
            "outbox_delivery": [_log_brief(item) for item in outbox_failures[-5:]],
            "outbox_dead_letter": [_log_brief(item) for item in outbox_dead_letters[-5:]],
            "ack_deadline": [_log_brief(item) for item in ack_deadline_misses[-5:]],
        },
        "diagnosis": diagnosis,
        "alerts": alerts,
    }


def build_trace_failure_diagnosis(
    *,
    logs: list[dict[str, Any]],
    jobs: dict[str, dict[str, Any]],
    events: list[dict[str, Any]],
    smoke: dict[str, Any],
    correlation: dict[str, Any],
    runtime_lock: dict[str, Any],
    service: dict[str, Any],
    alerts: list[str] | None = None,
) -> dict[str, Any]:
    """Promote runtime traces into a stable failure-attribution object."""

    alerts = alerts or []
    failed_jobs = [job for job in jobs.values() if job.get("status") == "failed"]
    rejected_jobs = [job for job in jobs.values() if job.get("status") == "rejected"]
    ack_misses = [
        item for item in logs
        if item.get("event") == "ws_event_received" and item.get("ack_within_deadline") is False
    ]
    outbox_dead_letters = [
        item for item in logs
        if item.get("event") == "outbox_delivery" and item.get("dead_letter") is True
    ]
    outbox_failures = [
        item for item in logs
        if item.get("event") == "outbox_delivery" and item.get("success") is False
    ]
    rejected_webhooks = [item for item in logs if item.get("event") == "webhook_rejected"]
    event_keys = [str(item.get("event_key", "")) for item in events if item.get("event_key")]

    candidates: list[tuple[str, str, str, list[dict[str, Any]]]] = []
    if service.get("last_status") == "failed":
        candidates.append((
            "service_failure",
            "Service exited with failure before evidence could complete.",
            "Inspect service_stop error_type and restart after fixing configuration or runtime exception.",
            [_trace_ref("runtime", "service_stop", service.get("error_type", ""))],
        ))
    if ack_misses:
        candidates.append((
            "ack_deadline_miss",
            "Feishu long-connection ACK breached the deadline.",
            "Keep ACK on the hot path and move slow work to the durable job queue.",
            [_trace_ref("runtime", "ws_event_received", _log_brief(item)) for item in ack_misses[-3:]],
        ))
    if failed_jobs:
        candidates.append((
            "runtime_job_failed",
            "A queued runtime job failed after ACK.",
            "Open the failed job error, reproduce it with the same event_key, then promote a regression if repeated.",
            [_trace_ref("job_store", str(job.get("id", "")), _job_brief(job)) for job in failed_jobs[-3:]],
        ))
    if rejected_jobs:
        candidates.append((
            "worker_backpressure",
            "Runtime worker saturation rejected one or more jobs.",
            "Increase worker capacity or shed load explicitly before Feishu retries pile up.",
            [_trace_ref("job_store", str(job.get("id", "")), _job_brief(job)) for job in rejected_jobs[-3:]],
        ))
    if outbox_dead_letters or outbox_failures:
        refs = outbox_dead_letters or outbox_failures
        candidates.append((
            "outbox_delivery_failed",
            "Reply delivery failed after processing completed.",
            "Check Feishu send response, token scope, and dead-letter replay before marking smoke complete.",
            [_trace_ref("runtime", "outbox_delivery", _log_brief(item)) for item in refs[-3:]],
        ))
    if rejected_webhooks:
        candidates.append((
            "webhook_rejected",
            "Incoming webhook was rejected before job creation.",
            "Verify Feishu token/signature configuration and replay the same event id.",
            [_trace_ref("runtime", "webhook_rejected", _log_brief(item)) for item in rejected_webhooks[-3:]],
        ))
    if correlation.get("missing"):
        candidates.append((
            "correlation_chain_incomplete",
            "Smoke evidence exists but runtime/job/event layers do not bind to the same event keys.",
            "Recollect smoke after service restart and verify event_key continuity across logs, jobs, and smoke records.",
            [_trace_ref("correlation", "missing", correlation.get("missing", []))],
        ))
    if not smoke.get("ok"):
        candidates.append((
            "smoke_evidence_incomplete",
            "Required smoke scenarios are missing or stale.",
            "Run the missing live smoke scenarios and rebuild the redacted bundle from that same session.",
            [_trace_ref("smoke", "missing", smoke.get("missing", []))],
        ))
    if runtime_lock.get("configured") and runtime_lock.get("ok") is False:
        candidates.append((
            "runtime_store_locked",
            "Another writer owns the runtime store lock.",
            "Stop the competing service or wait for lock expiry before collecting release evidence.",
            [_trace_ref("runtime_lock", runtime_lock.get("path", ""), runtime_lock.get("detail", ""))],
        ))
    if not event_keys and events:
        candidates.append((
            "event_store_key_missing",
            "Event store has records without usable Feishu event keys.",
            "Check event normalization before relying on duplicate or correlation proof.",
            [_trace_ref("event_store", "event_key", "missing")],
        ))

    root_cause, summary, action, refs = candidates[0] if candidates else (
        "none",
        "No failure cause detected from current traces.",
        "Continue with release verification.",
        [],
    )
    return {
        "schema": TRACE_FAILURE_DIAGNOSIS_SCHEMA,
        "root_cause": root_cause,
        "summary": summary,
        "suggested_action": action,
        "evidence_refs": refs,
        "candidate_count": len(candidates),
        "alerts": alerts,
        "trace_complete": bool(refs) or root_cause == "none",
        "smoke_ok": smoke.get("ok") is True,
        "correlation_ok": not bool(correlation.get("missing")),
    }


def format_diagnostics(summary: dict[str, Any]) -> str:
    """Render a compact human-readable diagnostic report."""

    status = "OK" if summary.get("ok") else "ATTENTION"
    lines = [
        f"YINYO diagnostics: {status}",
        f"runtime records: {summary['runtime']['records']}",
        _format_service_diagnostics(summary.get("runtime", {}).get("service", {})),
        _format_ws_diagnostics(summary.get("runtime", {}).get("ws", {})),
        f"job status: {summary['jobs']['status_counts']}",
        f"event store keys: {summary.get('event_store', {}).get('unique_event_keys', 0)}",
        f"runtime lock: {summary.get('runtime_lock', {}).get('status', 'unknown')}",
        f"root cause: {summary.get('diagnosis', {}).get('root_cause', 'unknown')}",
        f"smoke missing: {summary['smoke']['missing']}",
        f"correlation missing: {summary.get('correlation', {}).get('missing', [])}",
    ]
    alerts = summary.get("alerts", [])
    if alerts:
        lines.append("alerts:")
        lines.extend(f"- {item}" for item in alerts)
    return "\n".join(lines)


def _format_ws_diagnostics(ws: dict[str, Any]) -> str:
    return (
        "ws events: "
        f"{ws.get('events', 0)}, "
        f"ack_misses: {ws.get('ack_deadline_misses', 0)}, "
        f"max_ack_latency_ms: {ws.get('max_ack_latency_ms')}, "
        f"ack_deadline_ms: {ws.get('ack_deadline_ms')}"
    )


def _format_service_diagnostics(service: dict[str, Any]) -> str:
    return (
        "service: "
        f"started={service.get('started', False)}, "
        f"last_status={service.get('last_status', 'unknown')}, "
        f"transport={service.get('transport', '')}, "
        f"error_type={service.get('error_type', '')}"
    )


def _read_jsonl(path: str) -> list[dict[str, Any]]:
    if not os.path.isfile(path):
        return []
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                records.append(item)
    return records


def _latest_jobs(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    jobs = {}
    for item in records:
        job_id = item.get("id")
        if job_id:
            jobs[job_id] = item
    return jobs


def _build_alerts(
    logs: list[dict[str, Any]],
    jobs: dict[str, dict[str, Any]],
    smoke: dict[str, Any],
    outbox_failures: list[dict[str, Any]],
    outbox_dead_letters: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    ack_deadline_misses: list[dict[str, Any]],
    event_store_path: str,
    event_keys: list[str],
    runtime_lock: dict[str, Any],
    service: dict[str, Any],
    correlation: dict[str, Any],
) -> list[str]:
    alerts = []
    if not logs:
        alerts.append("runtime log has no records")
    if not jobs:
        alerts.append("job store has no jobs")
    failed_count = sum(1 for job in jobs.values() if job.get("status") == "failed")
    if failed_count:
        alerts.append(f"{failed_count} runtime job(s) failed")
    rejected_count = sum(1 for job in jobs.values() if job.get("status") == "rejected")
    if rejected_count:
        alerts.append(f"{rejected_count} runtime job(s) rejected by backpressure")
    abandoned_count = sum(1 for job in jobs.values() if job.get("status") == "abandoned")
    if abandoned_count:
        alerts.append(f"{abandoned_count} runtime job(s) abandoned after restart")
    if outbox_failures:
        alerts.append(f"{len(outbox_failures)} outbox delivery failure(s)")
    if outbox_dead_letters:
        alerts.append(f"{len(outbox_dead_letters)} outbox delivery dead-letter(s)")
    if rejected:
        alerts.append(f"{len(rejected)} rejected webhook event(s)")
    if ack_deadline_misses:
        alerts.append(f"{len(ack_deadline_misses)} Feishu event ack deadline miss(es)")
    if not smoke.get("ok"):
        missing = ", ".join(smoke.get("missing", []))
        alerts.append(f"live smoke evidence incomplete: {missing}")
    if event_store_path and not event_keys:
        alerts.append("event store has no Feishu event keys")
    if service.get("last_status") == "failed":
        error_type = service.get("error_type") or "unknown"
        alerts.append(f"service exited with failure: {error_type}")
    if correlation.get("missing"):
        missing = ", ".join(correlation.get("missing", []))
        alerts.append(f"correlation chain incomplete: {missing}")
    return alerts


def _runtime_lock_summary(path: str) -> dict[str, Any]:
    if not path:
        return {"configured": False, "ok": None, "status": "not_configured", "path": ""}
    ok, detail = check_runtime_store_lock_available(path)
    return {
        "configured": True,
        "ok": ok,
        "status": "available" if ok else "locked",
        "path": path,
        "detail": detail,
    }


def _ws_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    latencies = [
        item.get("ack_latency_ms")
        for item in records
        if isinstance(item.get("ack_latency_ms"), (int, float))
    ]
    deadlines = [
        item.get("ack_deadline_ms")
        for item in records
        if isinstance(item.get("ack_deadline_ms"), (int, float))
    ]
    return {
        "events": len(records),
        "ack_deadline_misses": sum(1 for item in records if item.get("ack_within_deadline") is False),
        "max_ack_latency_ms": max(latencies) if latencies else None,
        "ack_deadline_ms": deadlines[-1] if deadlines else None,
    }


def _service_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    starts = [item for item in records if item.get("event") == "service_start"]
    stops = [item for item in records if item.get("event") == "service_stop"]
    latest_start = starts[-1] if starts else {}
    latest_stop = stops[-1] if stops else {}
    return {
        "started": bool(starts),
        "start_count": len(starts),
        "stop_count": len(stops),
        "last_status": latest_stop.get("status", "running" if starts else "unknown"),
        "transport": latest_stop.get("transport") or latest_start.get("transport", ""),
        "profile": latest_start.get("profile", ""),
        "error_type": latest_stop.get("error_type", ""),
        "last_start_ts": latest_start.get("ts"),
        "last_stop_ts": latest_stop.get("ts"),
    }


def _last_value(records: list[dict[str, Any]], key: str) -> Any:
    for item in reversed(records):
        value = item.get(key)
        if value:
            return value
    return ""


def _job_brief(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": job.get("id", ""),
        "kind": job.get("kind", ""),
        "status": job.get("status", ""),
        "error": job.get("error", ""),
    }


def _log_brief(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "event": item.get("event", ""),
        "correlation_id": item.get("correlation_id", ""),
        "reason": item.get("reason", ""),
        "error": item.get("error", ""),
        "attempts": item.get("attempts", ""),
        "dead_letter": item.get("dead_letter", ""),
        "ack_latency_ms": item.get("ack_latency_ms", ""),
        "ack_deadline_ms": item.get("ack_deadline_ms", ""),
    }


def _trace_ref(layer: str, ref: str, detail: Any) -> dict[str, Any]:
    return {
        "layer": layer,
        "ref": str(ref),
        "detail": detail,
    }
