"""Redacted live-smoke evidence records."""

from __future__ import annotations

import json
import os
import hashlib
import re
import time
from pathlib import Path
from typing import Any

from .governance import redact_secrets
from .jsonl_store import append_jsonl
from .scenario import replay_release_matrix


class SmokeEvidenceRecorder:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    def record(self, scenario: str, status: str, **fields: Any) -> dict[str, Any]:
        redacted = {key: _redact_value(value) for key, value in fields.items()}
        entry = {
            "ts": time.time(),
            "scenario": scenario,
            "status": status,
            **redacted,
        }
        append_jsonl(self.path, entry)
        return entry


REQUIRED_1_0_SCENARIOS = {
    "url_verification",
    "text_message_reply",
    "image_message_reply",
    "card_fallback",
    "duplicate_callback",
}

REQUIRED_1_0_HTTP_SCENARIOS = frozenset(REQUIRED_1_0_SCENARIOS)

REQUIRED_1_0_WS_SCENARIOS = frozenset(
    scenario for scenario in REQUIRED_1_0_SCENARIOS if scenario != "url_verification"
)

REQUIRED_1_0_ADVANCED_SCENARIOS = {
    "image_understanding",
    "long_conversation",
    "memory_supersession",
    "trace2skill_promotion",
    "deepseek_usage",
    "partial_failure",
}

ADVANCED_LIVE_RECORDER = "yinyo smoke record-advanced"
ADVANCED_LIVE_PROOF_SCHEMA = "yinyo.advanced_live_proof.v1"

LIVE_SMOKE_SCENARIO_GUIDE = {
    "url_verification": "Enable the Feishu HTTP callback and complete real URL verification.",
    "text_message_reply": "Send a plain text message to the bot and confirm a YINYO reply is delivered.",
    "image_message_reply": "Send an image to the bot and confirm the image path produces a reply or a graceful vision fallback.",
    "card_fallback": "Temporarily set smoke_mode=true, restart the service, send `/yinyo-smoke card-fallback`, and confirm text fallback evidence.",
    "duplicate_callback": "Replay or receive the same callback event id twice and confirm only one job is processed.",
}

ADVANCED_LIVE_SCENARIO_GUIDE = {
    "image_understanding": "Run a real Feishu image workflow and attach image_ref or run_id showing useful image understanding or graceful unsupported-state language.",
    "long_conversation": "Run a real Feishu long conversation and attach a redacted transcript_ref or run_id.",
    "memory_supersession": "Demonstrate a real user fact superseding an older fact and attach memory_ref or run_id.",
    "trace2skill_promotion": "Promote a real repeated-failure skill only after regression replay validation and attach failure_trace_ref, skill_ref, validation_ref or regression_result_ref, promotion_status, and post_promotion_run_ref.",
    "deepseek_usage": "Attach model_usage or usage_ref from a real Feishu run with token/cost telemetry.",
    "partial_failure": "Trigger a real partial-failure path and attach failure_ref or run_id showing user-visible degradation.",
}

ADVANCED_LIVE_REQUIRED_FIELDS = {
    "image_understanding": (("image_ref", "run_id"),),
    "long_conversation": (("transcript_ref", "run_id"),),
    "memory_supersession": (("memory_ref", "run_id"),),
    "trace2skill_promotion": (
        ("failure_trace_ref",),
        ("skill_ref",),
        ("validation_ref", "regression_result_ref", "regression_ref"),
        ("promotion_status",),
        ("post_promotion_run_ref",),
    ),
    "deepseek_usage": (("model_usage", "usage_ref"),),
    "partial_failure": (("failure_ref", "run_id"),),
}

REQUIRED_3_6_LOCAL_EVIDENCE = {
    "long_conversation": "long-context retention and masking",
    "memory_supersession": "fact supersession and audit trail",
    "trace2skill_promotion": "Trace2Skill extraction, regression replay validation, and promotion",
    "deepseek_usage": "DeepSeek token/cost telemetry",
    "card_fallback": "rich-card fallback behavior",
    "partial_failure": "visible partial failure and blocked evidence",
    "release_gate": "1.0 release gate blocks missing live evidence",
}

SMOKE_RUNTIME_EVENTS = {
    "url_verification": {"webhook_url_verification", "webhook_accepted", "ws_event_received"},
    "text_message_reply": {"outbox_delivery"},
    "image_message_reply": {"outbox_delivery"},
    "card_fallback": {"outbox_delivery"},
    "duplicate_callback": {"webhook_duplicate"},
}


def required_live_smoke_scenarios(transport: str | None = None) -> frozenset[str]:
    """Return required basic live-smoke scenarios for the selected Feishu transport."""

    if (transport or "").strip().lower() == "ws":
        return REQUIRED_1_0_WS_SCENARIOS
    return REQUIRED_1_0_HTTP_SCENARIOS


def load_smoke_evidence(path: str) -> list[dict[str, Any]]:
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


def verify_smoke_evidence(path: str, required: set[str] | None = None) -> dict[str, Any]:
    required = required or REQUIRED_1_0_SCENARIOS
    records = load_smoke_evidence(path)
    passed = {
        item.get("scenario")
        for item in records
        if item.get("status") == "passed" and item.get("live") is True
    }
    missing = sorted(required - passed)
    return {
        "ok": not missing,
        "path": path,
        "required": sorted(required),
        "passed": sorted(passed),
        "missing": missing,
        "records": len(records),
    }


def verify_advanced_live_evidence(path: str, required: set[str] | None = None, *, resolve_refs: bool = True) -> dict[str, Any]:
    """Verify live evidence for the non-basic 3+6 product scenarios."""
    required = required or REQUIRED_1_0_ADVANCED_SCENARIOS
    records = load_smoke_evidence(path)
    evidence_root = Path(path).resolve().parent
    latest = {
        str(item.get("scenario", "")): item
        for item in records
        if item.get("status") == "passed" and item.get("live") is True
    }
    missing = []
    field_missing = []
    source_missing = []
    proof_missing = []
    proof_mismatch = []
    ref_unresolved = []
    ref_status: dict[str, dict[str, Any]] = {}
    for scenario in sorted(required):
        record = latest.get(scenario)
        if not record:
            missing.append(scenario)
            continue
        if record.get("evidence_source") != ADVANCED_LIVE_RECORDER:
            source_missing.append(scenario)
        for alternatives in ADVANCED_LIVE_REQUIRED_FIELDS.get(scenario, ()):
            if not any(record.get(field) not in (None, "", [], {}) for field in alternatives):
                field_missing.append(f"{scenario}:{'|'.join(alternatives)}")
        proof = record.get("advanced_proof")
        expected = _build_advanced_live_proof(scenario, record)
        if not isinstance(proof, dict) or not proof.get("digest"):
            proof_missing.append(scenario)
        elif proof != expected:
            proof_mismatch.append(scenario)
        if resolve_refs:
            resolved = _resolve_advanced_refs(scenario, record, evidence_root=evidence_root)
            ref_status[scenario] = resolved
            ref_unresolved.extend(f"{scenario}:{item}" for item in resolved.get("unresolved", []))
        else:
            ref_status[scenario] = {
                "schema": "yinyo.advanced_ref_resolution.v1",
                "scenario": scenario,
                "resolved": {},
                "unresolved": [],
                "ok": True,
                "mode": "skipped_for_redacted_bundle",
            }
    return {
        "ok": not missing and not field_missing and not source_missing and not proof_missing and not proof_mismatch and not ref_unresolved,
        "path": path,
        "required": sorted(required),
        "passed": sorted(set(latest) & required),
        "missing": missing,
        "field_missing": field_missing,
        "source_missing": source_missing,
        "proof_missing": proof_missing,
        "proof_mismatch": proof_mismatch,
        "ref_unresolved": ref_unresolved,
        "ref_status": ref_status,
        "ref_resolution_enabled": resolve_refs,
        "records": len(records),
    }


def verify_smoke_evidence_file(path: str, transport: str | None = None) -> dict[str, Any]:
    """Verify required basic and advanced live records in one smoke evidence file."""
    basic = verify_smoke_evidence(path, required=set(required_live_smoke_scenarios(transport)))
    advanced = verify_advanced_live_evidence(path)
    missing = [f"basic:{scenario}" for scenario in basic["missing"]]
    missing.extend(f"advanced:{scenario}" for scenario in advanced["missing"])
    missing.extend(f"advanced_field:{field}" for field in advanced["field_missing"])
    missing.extend(f"advanced_source:{scenario}" for scenario in advanced["source_missing"])
    missing.extend(f"advanced_proof_missing:{scenario}" for scenario in advanced.get("proof_missing", []))
    missing.extend(f"advanced_proof_mismatch:{scenario}" for scenario in advanced.get("proof_mismatch", []))
    missing.extend(f"advanced_ref_unresolved:{item}" for item in advanced.get("ref_unresolved", []))
    return {
        "ok": basic["ok"] and advanced["ok"],
        "path": path,
        "basic": basic,
        "advanced": advanced,
        "missing": missing,
        "records": max(basic["records"], advanced["records"]),
    }


def record_advanced_live_evidence(path: str, scenario: str, **fields: Any) -> dict[str, Any]:
    """Record one validated advanced live evidence item and return the new status."""
    if scenario not in REQUIRED_1_0_ADVANCED_SCENARIOS:
        allowed = ", ".join(sorted(REQUIRED_1_0_ADVANCED_SCENARIOS))
        raise ValueError(f"unsupported advanced live scenario: {scenario}; allowed: {allowed}")

    cleaned = {key: value for key, value in fields.items() if value not in (None, "", [], {})}
    missing = []
    for alternatives in ADVANCED_LIVE_REQUIRED_FIELDS.get(scenario, ()):
        if not any(cleaned.get(field) not in (None, "", [], {}) for field in alternatives):
            missing.append("|".join(alternatives))
    if missing:
        raise ValueError(f"missing required evidence fields for {scenario}: {', '.join(missing)}")
    if scenario == "trace2skill_promotion":
        status = str(cleaned.get("promotion_status", ""))
        if status not in {"proven", "stable"}:
            raise ValueError("promotion_status for trace2skill_promotion must be proven or stable")

    unresolved = _validate_advanced_live_refs_before_write(path, scenario, cleaned)
    if unresolved:
        raise ValueError(f"advanced evidence refs unresolved for {scenario}: {', '.join(unresolved)}")

    proof = _build_advanced_live_proof(scenario, cleaned)
    record = SmokeEvidenceRecorder(path).record(
        scenario,
        "passed",
        live=True,
        evidence_source=ADVANCED_LIVE_RECORDER,
        advanced_proof=proof,
        **cleaned,
    )
    return {
        "ok": True,
        "record": record,
        "advanced": verify_advanced_live_evidence(path),
    }


def _validate_advanced_live_refs_before_write(path: str, scenario: str, record: dict[str, Any]) -> list[str]:
    """Resolve local advanced refs before appending records so bad paths do not pollute smoke JSONL."""

    evidence_root = Path(path).resolve().parent
    resolved = _resolve_advanced_refs(scenario, record, evidence_root=evidence_root)
    return list(resolved.get("unresolved", []))


def verify_smoke_evidence_chain(
    *,
    smoke_path: str,
    log_path: str,
    job_store_path: str,
    event_store_path: str,
    required: set[str] | None = None,
    transport: str = "",
) -> dict[str, Any]:
    """Verify that live smoke evidence is backed by runtime artifacts."""
    required = required or REQUIRED_1_0_SCENARIOS
    smoke = verify_smoke_evidence(smoke_path, required=required)
    smoke_records = load_smoke_evidence(smoke_path)
    logs = _load_jsonl(log_path)
    jobs = _load_jsonl(job_store_path)
    events = _load_jsonl(event_store_path)
    event_keys = {
        str(item.get("event_key", ""))
        for item in events
        if item.get("event_key")
    }
    latest_jobs = _latest_job_records(jobs)
    session = _smoke_session_boundary(smoke_records=smoke_records, logs=logs, jobs=jobs, events=events, required=required)
    correlation = verify_correlation_chains(
        smoke_records=smoke_records,
        logs=logs,
        jobs=jobs,
        events=events,
        required=required,
        transport=transport,
    )
    missing: list[str] = []

    if not smoke["ok"]:
        missing.extend(f"smoke:{scenario}" for scenario in smoke["missing"])
    missing.extend(session["missing"])

    passed_smoke_records = {
        str(item.get("scenario", "")): item
        for item in smoke_records
        if item.get("status") == "passed" and item.get("live") is True
    }

    for scenario in sorted(required):
        record = passed_smoke_records.get(scenario, {})
        event_key = str(record.get("event_key", ""))
        scenario_logs = _scenario_runtime_logs(logs, scenario=scenario, event_key=event_key)
        backed = bool(SMOKE_RUNTIME_EVENTS.get(scenario, set()) & {str(item.get("event", "")) for item in scenario_logs})
        if not backed:
            missing.append(f"runtime_log:{scenario}")

    for scenario in ("text_message_reply", "image_message_reply", "card_fallback"):
        record = passed_smoke_records.get(scenario, {})
        if not _scenario_has_outbox_success(logs, scenario=scenario, event_key=str(record.get("event_key", ""))):
            missing.append(f"outbox_success:{scenario}")

    if not any(job.get("kind") == "feishu_message" and job.get("status") == "succeeded" for job in latest_jobs.values()):
        missing.append("job_store:feishu_message_succeeded")

    if not event_keys:
        missing.append("event_store:seen_event_key")

    duplicate_keys = {
        str(item.get("event_key", ""))
        for item in logs
        if item.get("event") == "webhook_duplicate" and item.get("event_key")
    }
    duplicate_record = passed_smoke_records.get("duplicate_callback", {})
    duplicate_event_key = str(duplicate_record.get("event_key", ""))
    if "duplicate_callback" in required and not duplicate_event_key:
        missing.append("smoke:duplicate_event_key")
    if "duplicate_callback" in required and duplicate_event_key and duplicate_event_key not in event_keys:
        missing.append("event_store:duplicate_event_key")
    if "duplicate_callback" in required and duplicate_event_key and duplicate_event_key not in duplicate_keys:
        missing.append("runtime_log:duplicate_event_key")
    for scenario in sorted(required):
        if scenario not in {"text_message_reply", "image_message_reply", "card_fallback"}:
            continue
        record = passed_smoke_records.get(scenario, {})
        event_key = str(record.get("event_key", ""))
        job = _scenario_job_record(jobs, event_key=event_key)
        if job and job.get("status") != "succeeded":
            missing.append(f"job_store:{scenario}:status")
    if (transport or "").strip().lower() == "ws":
        for scenario in sorted(required - {"url_verification"}):
            record = passed_smoke_records.get(scenario, {})
            event_key = str(record.get("event_key", ""))
            ws = _scenario_ws_ack_status(logs, event_key=event_key)
            if not ws["seen"]:
                missing.append(f"ws_event_received:{scenario}")
            elif ws["ack_within_deadline"] is not True:
                missing.append(f"ws_ack:{scenario}")
            if ws["seen"] and (ws["ack_latency_ms"] in (None, "") or ws["ack_deadline_ms"] in (None, "")):
                missing.append(f"ws_ack_metrics:{scenario}")
    missing.extend(correlation["missing"])

    return {
        "ok": not missing,
        "smoke": smoke,
        "correlation": correlation,
        "session": session,
        "paths": {
            "smoke_evidence": smoke_path,
            "runtime_log": log_path,
            "job_store": job_store_path,
            "event_store": event_store_path,
        },
        "records": {
            "smoke": smoke["records"],
            "runtime_log": len(logs),
            "job_store": len(jobs),
            "event_store": len(events),
        },
        "missing": sorted(set(missing)),
    }


def verify_correlation_chains(
    *,
    smoke_records: list[dict[str, Any]],
    logs: list[dict[str, Any]],
    jobs: list[dict[str, Any]],
    events: list[dict[str, Any]],
    required: set[str] | None = None,
    transport: str = "",
) -> dict[str, Any]:
    """Verify event-key continuity across smoke, runtime, job, and event stores."""

    required = required or REQUIRED_1_0_SCENARIOS
    passed_smoke_records = {
        str(item.get("scenario", "")): item
        for item in smoke_records
        if item.get("status") == "passed" and item.get("live") is True
    }
    session = _smoke_session_boundary(smoke_records=smoke_records, logs=logs, jobs=jobs, events=events, required=required)
    event_keys = {
        str(item.get("event_key", ""))
        for item in events
        if item.get("event_key")
    }
    chains: list[dict[str, Any]] = []
    missing: list[str] = []
    for scenario in sorted(required):
        record = passed_smoke_records.get(scenario, {})
        event_key = str(record.get("event_key", ""))
        if not event_key:
            if scenario != "url_verification":
                missing.append(f"correlation:{scenario}:smoke_event_key")
            continue
        runtime_events = _scenario_runtime_logs(logs, scenario=scenario, event_key=event_key)
        job = _scenario_job_record(jobs, event_key=event_key)
        job_required = scenario in {"text_message_reply", "image_message_reply", "card_fallback", "duplicate_callback"}
        event_store_required = scenario != "url_verification"
        smoke_ok = bool(record)
        runtime_ok = bool(runtime_events)
        if scenario == "duplicate_callback":
            runtime_ok = any(item.get("event") == "webhook_duplicate" for item in runtime_events)
        ws = _scenario_ws_ack_status(logs, event_key=event_key)
        job_status_ok = (not job_required) or (bool(job) and (scenario == "duplicate_callback" or job.get("status") == "succeeded"))
        job_ok = (not job_required) or job_status_ok
        event_store_ok = (not event_store_required) or event_key in event_keys
        missing_layers = []
        if not smoke_ok:
            missing_layers.append("smoke")
        if not runtime_ok:
            missing_layers.append("runtime_log")
        if not job_ok:
            missing_layers.append("job_store")
        if not event_store_ok:
            missing_layers.append("event_store")
        if (transport or "").strip().lower() == "ws" and scenario != "url_verification":
            if not ws["seen"]:
                missing_layers.append("ws_event_received")
            elif ws["ack_within_deadline"] is not True:
                missing_layers.append("ws_ack")
            if ws["seen"] and (ws["ack_latency_ms"] in (None, "") or ws["ack_deadline_ms"] in (None, "")):
                missing_layers.append("ws_ack_metrics")
        for layer in missing_layers:
            missing.append(f"correlation:{scenario}:{layer}")
        chains.append({
            "scenario": scenario,
            "event_key": event_key,
            "ok": not missing_layers,
            "layers": {
                "smoke": smoke_ok,
                "runtime_log": runtime_ok,
                "job_store": job_ok,
                "event_store": event_store_ok,
            },
            "runtime_events": sorted({str(item.get("event", "")) for item in runtime_events if item.get("event")}),
            "job_id": job.get("id", ""),
            "job_status": job.get("status", ""),
            "ws": ws,
            "missing": missing_layers,
        })
    return {
        "ok": not missing,
        "chains": chains,
        "missing": sorted(set(missing)),
    }


def wait_for_smoke_evidence_chain(
    *,
    smoke_path: str,
    log_path: str,
    job_store_path: str,
    event_store_path: str,
    runtime_lock_path: str = "",
    transport: str = "",
    config_path: str = "./yinyo.env",
    timeout_seconds: float = 300,
    interval_seconds: float = 2,
    required: set[str] | None = None,
) -> dict[str, Any]:
    """Poll live smoke evidence until the full chain is complete or timed out."""
    deadline = time.time() + max(0, timeout_seconds)
    attempts = 0
    last = verify_full_smoke_evidence(
        smoke_path=smoke_path,
        log_path=log_path,
        job_store_path=job_store_path,
        event_store_path=event_store_path,
        required=required,
        transport=transport,
    )
    while True:
        attempts += 1
        if last["ok"]:
            status = build_smoke_evidence_status(
                smoke_path=smoke_path,
                log_path=log_path,
                job_store_path=job_store_path,
                event_store_path=event_store_path,
                runtime_lock_path=runtime_lock_path,
                transport=transport,
                config_path=config_path,
                required=required,
            )
            return {
                "ok": True,
                "timed_out": False,
                "attempts": attempts,
                "chain": last,
                "operator_next_actions": status["next_actions"],
                "operator_plan": status["operator_plan"],
                "handoff_summary": status["handoff_summary"],
            }
        if time.time() >= deadline:
            status = build_smoke_evidence_status(
                smoke_path=smoke_path,
                log_path=log_path,
                job_store_path=job_store_path,
                event_store_path=event_store_path,
                runtime_lock_path=runtime_lock_path,
                transport=transport,
                config_path=config_path,
                required=required,
            )
            return {
                "ok": False,
                "timed_out": True,
                "attempts": attempts,
                "chain": last,
                "operator_next_actions": status["next_actions"],
                "operator_plan": status["operator_plan"],
                "handoff_summary": status["handoff_summary"],
            }
        time.sleep(max(0.1, interval_seconds))
        last = verify_full_smoke_evidence(
            smoke_path=smoke_path,
            log_path=log_path,
            job_store_path=job_store_path,
            event_store_path=event_store_path,
            required=required,
            transport=transport,
        )


def build_smoke_evidence_status(
    *,
    smoke_path: str,
    log_path: str,
    job_store_path: str,
    event_store_path: str,
    runtime_lock_path: str = "",
    profile: str = "",
    transport: str = "",
    config_path: str = "./yinyo.env",
    required: set[str] | None = None,
) -> dict[str, Any]:
    """Return a read-only operator status for the live smoke evidence chain."""
    required = required or REQUIRED_1_0_SCENARIOS
    chain = verify_full_smoke_evidence(
        smoke_path=smoke_path,
        log_path=log_path,
        job_store_path=job_store_path,
        event_store_path=event_store_path,
        required=required,
        transport=transport,
    )
    smoke_records = load_smoke_evidence(smoke_path)
    logs = _load_jsonl(log_path)
    events = _load_jsonl(event_store_path)
    jobs = _load_jsonl(job_store_path)
    event_keys = {str(item.get("event_key", "")) for item in events if item.get("event_key")}
    session = _smoke_session_boundary(smoke_records=smoke_records, logs=logs, jobs=jobs, events=events, required=required)
    passed_smoke_records = {
        str(item.get("scenario", "")): item
        for item in smoke_records
        if item.get("status") == "passed" and item.get("live") is True
    }
    latest_jobs = _latest_job_records(jobs)
    has_successful_message_job = any(
        job.get("kind") == "feishu_message" and job.get("status") == "succeeded"
        for job in latest_jobs.values()
    )

    scenarios = []
    for scenario in sorted(required):
        smoke_record = passed_smoke_records.get(scenario, {})
        event_key = str(smoke_record.get("event_key", ""))
        scenario_logs = _scenario_runtime_logs(logs, scenario=scenario, event_key=event_key)
        scenario_job = _scenario_job_record(jobs, event_key=event_key)
        ws = _scenario_ws_ack_status(logs, event_key=event_key)
        scenario_log_events = {str(item.get("event", "")) for item in scenario_logs}
        runtime_backed = bool(SMOKE_RUNTIME_EVENTS.get(scenario, set()) & scenario_log_events)
        outbox_backed = scenario not in {"text_message_reply", "image_message_reply", "card_fallback"} or _scenario_has_outbox_success(
            logs,
            scenario=scenario,
            event_key=event_key,
        )
        job_required = scenario in {"text_message_reply", "image_message_reply", "card_fallback", "duplicate_callback"}
        job_status_backed = (not job_required) or (
            bool(scenario_job)
            and (scenario == "duplicate_callback" or scenario_job.get("status") == "succeeded")
        )
        job_backed = (not job_required) or job_status_backed
        event_store_required = scenario != "url_verification"
        event_backed = (not event_store_required) or bool(event_key and event_key in event_keys)
        duplicate_log_backed = scenario != "duplicate_callback" or any(
            item.get("event") == "webhook_duplicate" and item.get("event_key") == event_key
            for item in logs
        )
        missing = []
        if not smoke_record:
            missing.append("smoke_record")
        if not runtime_backed:
            missing.append("runtime_log")
        if not outbox_backed:
            missing.append("outbox_delivery")
        if not job_backed:
            missing.append("job_store_status" if scenario_job else "job_store")
        if not event_backed:
            missing.append("event_store")
        if not duplicate_log_backed:
            missing.append("duplicate_runtime_log")
        if scenario in session.get("stale_scenarios", []):
            missing.append("stale_session")
        if (transport or "").strip().lower() == "ws" and scenario != "url_verification":
            if not ws["seen"]:
                missing.append("ws_event_received")
            elif ws["ack_within_deadline"] is not True:
                missing.append("ws_ack")
            if ws["seen"] and (ws["ack_latency_ms"] in (None, "") or ws["ack_deadline_ms"] in (None, "")):
                missing.append("ws_ack_metrics")
        scenarios.append({
            "scenario": scenario,
            "ok": not missing,
            "event_key": event_key,
            "smoke_record_ts": smoke_record.get("ts"),
            "job_id": scenario_job.get("id", ""),
            "run_id": _extract_run_id(scenario_job),
            "message_ids": _scenario_message_ids(scenario_logs, scenario_job),
            "runtime_events_seen": sorted({str(item.get("event", "")) for item in scenario_logs if item.get("event")}),
            "ws_event_seen": ws["seen"],
            "ws_ack_within_deadline": ws["ack_within_deadline"],
            "ws_ack_latency_ms": ws["ack_latency_ms"],
            "ws_ack_deadline_ms": ws["ack_deadline_ms"],
            "job_ref": scenario_job.get("id", ""),
            "job_status": scenario_job.get("status", ""),
            "last_error": scenario_job.get("error", ""),
            "missing": missing,
            "operator_action": LIVE_SMOKE_SCENARIO_GUIDE.get(scenario, ""),
        })

    next_actions = [
        item["operator_action"]
        for item in scenarios
        if not item["ok"] and item.get("operator_action")
    ]
    if not has_successful_message_job:
        next_actions.append("Confirm at least one Feishu message job reaches status=succeeded in runtime_jobs.jsonl.")
    if not event_keys:
        next_actions.append("Confirm gateway_events.jsonl records the Feishu event keys seen during live smoke.")
    if session["missing"]:
        next_actions.append("Run yinyo smoke reset, restart yinyo serve, and collect all basic smoke scenarios after the latest service_start.")
    advanced = chain["advanced"]
    advanced_records = {
        str(item.get("scenario", "")): item
        for item in smoke_records
        if item.get("status") == "passed" and item.get("live") is True
    }
    advanced_ref_unresolved_by_scenario = {
        scenario: [
            item
            for item in advanced.get("ref_unresolved", [])
            if item.startswith(f"{scenario}:")
        ]
        for scenario in sorted(REQUIRED_1_0_ADVANCED_SCENARIOS)
    }
    advanced_scenarios = [
        {
            "scenario": scenario,
            "ok": scenario in advanced["passed"]
            and not any(item.startswith(f"{scenario}:") for item in advanced["field_missing"])
            and scenario not in advanced.get("source_missing", [])
            and scenario not in advanced.get("proof_missing", [])
            and scenario not in advanced.get("proof_mismatch", [])
            and not advanced_ref_unresolved_by_scenario.get(scenario, []),
            "missing": (
                ["smoke_record"] if scenario in advanced["missing"] else []
            )
            + (["controlled_recorder"] if scenario in advanced.get("source_missing", []) else [])
            + (["proof"] if scenario in advanced.get("proof_missing", []) else [])
            + (["proof_digest"] if scenario in advanced.get("proof_mismatch", []) else [])
            + [
                f"ref:{item.split(':', 1)[1]}"
                for item in advanced_ref_unresolved_by_scenario.get(scenario, [])
            ]
            + [
                f"field:{item.split(':', 1)[1]}"
                for item in advanced["field_missing"]
                if item.startswith(f"{scenario}:")
            ],
            "required_fields": [
                "|".join(fields)
                for fields in ADVANCED_LIVE_REQUIRED_FIELDS.get(scenario, ())
            ],
            "present_fields": _present_advanced_fields(advanced_records.get(scenario, {})),
            "evidence_source": advanced_records.get(scenario, {}).get("evidence_source", ""),
            "proof_schema": advanced_records.get(scenario, {}).get("advanced_proof", {}).get("schema", "")
            if isinstance(advanced_records.get(scenario, {}).get("advanced_proof"), dict)
            else "",
            "proof_digest": advanced_records.get(scenario, {}).get("advanced_proof", {}).get("digest", "")
            if isinstance(advanced_records.get(scenario, {}).get("advanced_proof"), dict)
            else "",
            "ref_status": advanced.get("ref_status", {}).get(scenario, {}),
            "record_ts": advanced_records.get(scenario, {}).get("ts"),
            "refs": _advanced_refs(advanced_records.get(scenario, {})),
            "operator_action": ADVANCED_LIVE_SCENARIO_GUIDE.get(scenario, ""),
        }
        for scenario in sorted(REQUIRED_1_0_ADVANCED_SCENARIOS)
    ]
    next_actions.extend(
        item["operator_action"]
        for item in advanced_scenarios
        if not item["ok"] and item.get("operator_action")
    )
    operator_plan = _build_operator_plan(
        scenarios=scenarios,
        advanced_scenarios=advanced_scenarios,
        has_successful_message_job=has_successful_message_job,
        event_keys=event_keys,
        config_path=config_path,
    )
    diagnostics = _status_diagnostics(
        smoke_path=smoke_path,
        log_path=log_path,
        job_store_path=job_store_path,
        event_store_path=event_store_path,
        runtime_lock_path=runtime_lock_path,
        transport=transport,
    )
    recovery_summary = _build_recovery_summary(diagnostics)
    frontier_readiness = _build_frontier_readiness(
        root=Path(__file__).resolve().parents[1],
        chain=chain,
        advanced=advanced,
        diagnostics=diagnostics,
        handoff_records=0,
        bundle_verified=False,
    )
    handoff_summary = _build_handoff_summary(
        ok=chain["ok"],
        operator_plan=operator_plan,
        recovery_summary=recovery_summary,
        frontier_readiness=frontier_readiness,
    )
    return {
        "ok": chain["ok"],
        "snapshot": {
            "generated_at": time.time(),
            "profile": profile,
            "transport": transport,
            "paths": {
                "smoke_evidence": smoke_path,
                "runtime_log": log_path,
                "job_store": job_store_path,
                "event_store": event_store_path,
                "runtime_lock": runtime_lock_path,
            },
            "record_counts": {
                "smoke": len(smoke_records),
                "runtime_log": len(logs),
                "job_store": len(jobs),
                "event_store": len(events),
            },
            "latest_timestamps": {
                "smoke": _latest_ts(smoke_records),
                "runtime_log": _latest_ts(logs),
                "job_store": _latest_ts(jobs),
                "event_store": _latest_ts(events),
            },
        },
        "chain": chain,
        "advanced": advanced,
        "scenarios": scenarios,
        "session": session,
        "advanced_scenarios": advanced_scenarios,
        "job_store": {"feishu_message_succeeded": has_successful_message_job},
        "event_store": {"seen_event_keys": sorted(event_keys)},
        "next_actions": _dedupe(next_actions),
        "operator_plan": operator_plan,
        "recovery_summary": recovery_summary,
        "frontier_readiness": frontier_readiness,
        "handoff_summary": handoff_summary,
        "correlation": chain.get("correlation", {}),
}


def _latest_ts(records: list[dict[str, Any]]) -> float | None:
    values = [
        item.get("ts") or item.get("updated_at") or item.get("created_at")
        for item in records
        if isinstance(item, dict)
    ]
    numeric = [float(value) for value in values if isinstance(value, int | float)]
    return max(numeric) if numeric else None


def _scenario_runtime_logs(logs: list[dict[str, Any]], *, scenario: str, event_key: str) -> list[dict[str, Any]]:
    expected_events = SMOKE_RUNTIME_EVENTS.get(scenario, set())
    if event_key:
        return [
            item
            for item in logs
            if (
                str(item.get("event_key", "")) == event_key
                or str(item.get("correlation_id", "")) == event_key
            )
        ]
    return [
        item
        for item in logs
        if str(item.get("event", "")) in expected_events
    ]


def _scenario_ws_ack_status(logs: list[dict[str, Any]], *, event_key: str) -> dict[str, Any]:
    if not event_key:
        return {
            "seen": False,
            "ack_within_deadline": False,
            "ack_latency_ms": None,
            "ack_deadline_ms": None,
        }
    matches = [
        item
        for item in logs
        if item.get("event") == "ws_event_received"
        and (
            str(item.get("event_key", "")) == event_key
            or str(item.get("correlation_id", "")) == event_key
        )
    ]
    latest = matches[-1] if matches else {}
    return {
        "seen": bool(matches),
        "ack_within_deadline": latest.get("ack_within_deadline") is True,
        "ack_latency_ms": latest.get("ack_latency_ms"),
        "ack_deadline_ms": latest.get("ack_deadline_ms"),
    }


def _smoke_session_boundary(
    *,
    smoke_records: list[dict[str, Any]],
    logs: list[dict[str, Any]],
    jobs: list[dict[str, Any]],
    events: list[dict[str, Any]],
    required: set[str],
) -> dict[str, Any]:
    service_starts = [item for item in logs if item.get("event") == "service_start" and isinstance(item.get("ts"), int | float)]
    latest_start_ts = max((float(item.get("ts", 0)) for item in service_starts), default=None)
    latest = {
        str(item.get("scenario", "")): item
        for item in smoke_records
        if item.get("status") == "passed" and item.get("live") is True
    }
    stale_scenarios: list[str] = []
    allowed_probe_scenarios: list[str] = []
    if latest_start_ts is not None:
        for scenario in sorted(required):
            record = latest.get(scenario)
            if not record or scenario == "url_verification":
                continue
            ts = record.get("ts")
            if isinstance(ts, int | float) and float(ts) < latest_start_ts:
                if scenario == "card_fallback" and _is_allowed_card_fallback_probe(record, service_starts):
                    allowed_probe_scenarios.append(scenario)
                    continue
                stale_scenarios.append(scenario)
    event_times: list[float] = []
    for scenario in sorted(required - {"url_verification"}):
        if scenario in allowed_probe_scenarios:
            continue
        event_key = str(latest.get(scenario, {}).get("event_key", ""))
        if not event_key:
            continue
        event_times.extend(_event_key_times(logs, event_key))
        event_times.extend(_event_key_times(jobs, event_key))
        event_times.extend(_event_key_times(events, event_key))
    spans_service_starts = 0
    if event_times:
        first = min(event_times)
        last = max(event_times)
        spans_service_starts = sum(1 for item in service_starts if first < float(item.get("ts", 0)) < last)
    missing: list[str] = []
    if stale_scenarios:
        missing.extend(f"smoke_session:stale:{scenario}" for scenario in stale_scenarios)
    if spans_service_starts:
        missing.append("smoke_session:multiple_service_starts")
    return {
        "schema": "yinyo.smoke_session_boundary.v1",
        "latest_service_start_ts": latest_start_ts,
        "service_start_count": len(service_starts),
        "spans_service_starts": spans_service_starts,
        "stale_scenarios": stale_scenarios,
        "allowed_probe_scenarios": allowed_probe_scenarios,
        "missing": missing,
        "ok": not missing,
    }


def _is_allowed_card_fallback_probe(record: dict[str, Any], service_starts: list[dict[str, Any]]) -> bool:
    ts = record.get("ts")
    if not isinstance(ts, int | float):
        return False
    record_ts = float(ts)
    starts = sorted(
        (item for item in service_starts if isinstance(item.get("ts"), int | float)),
        key=lambda item: float(item.get("ts", 0)),
    )
    if len(starts) < 2:
        return False
    latest = starts[-1]
    latest_ts = float(latest.get("ts", 0))
    if latest.get("smoke_mode") is not False or not (record_ts < latest_ts):
        return False
    previous_index = None
    for index, item in enumerate(starts[:-1]):
        if float(item.get("ts", 0)) <= record_ts:
            previous_index = index
    if previous_index is None:
        return False
    if previous_index != len(starts) - 2:
        return False
    probe_start = starts[previous_index]
    return probe_start.get("smoke_mode") is True


def _event_key_times(records: list[dict[str, Any]], event_key: str) -> list[float]:
    values: list[float] = []
    for item in records:
        payload = item.get("payload", {}) if isinstance(item.get("payload"), dict) else {}
        result = item.get("result", {}) if isinstance(item.get("result"), dict) else {}
        if not (
            str(item.get("event_key", "")) == event_key
            or str(item.get("correlation_id", "")) == event_key
            or str(payload.get("event_key", "")) == event_key
            or str(result.get("event_key", "")) == event_key
        ):
            continue
        for key in ("ts", "recorded_at", "created_at", "started_at", "finished_at"):
            value = item.get(key)
            if isinstance(value, int | float):
                values.append(float(value))
    return values


def _scenario_job_record(jobs: list[dict[str, Any]], *, event_key: str) -> dict[str, Any]:
    if not event_key:
        return {}
    for job in reversed(jobs):
        payload = job.get("payload", {}) if isinstance(job.get("payload"), dict) else {}
        result = job.get("result", {}) if isinstance(job.get("result"), dict) else {}
        if (
            str(job.get("correlation_id", "")) == event_key
            or str(payload.get("event_key", "")) == event_key
            or str(result.get("event_key", "")) == event_key
        ):
            return job
    return {}


def _extract_run_id(job: dict[str, Any]) -> str:
    result = job.get("result", {}) if isinstance(job.get("result"), dict) else {}
    return str(result.get("run_id", ""))


def _scenario_message_ids(logs: list[dict[str, Any]], job: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    result = job.get("result", {}) if isinstance(job.get("result"), dict) else {}
    ids.extend(str(item) for item in result.get("message_ids", []) if item)
    for item in logs:
        for message_id in item.get("message_ids", []) or []:
            if message_id:
                ids.append(str(message_id))
    return sorted(set(ids))


def _present_advanced_fields(record: dict[str, Any]) -> list[str]:
    ignored = {"ts", "scenario", "status", "live", "evidence_source"}
    return sorted(
        key
        for key, value in record.items()
        if key not in ignored and value not in (None, "", [], {})
    )


def _advanced_refs(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in record.items()
        if key.endswith("_ref") or key == "run_id"
    }


def _resolve_advanced_refs(scenario: str, record: dict[str, Any], *, evidence_root: Path) -> dict[str, Any]:
    refs = _advanced_refs(record)
    resolved: dict[str, Any] = {}
    unresolved: list[str] = []
    for field, value in refs.items():
        status = _resolve_advanced_ref(field, value, evidence_root=evidence_root)
        resolved[field] = status
        if status.get("status") == "unresolved":
            unresolved.append(f"{field}:{status.get('reason', 'unresolved')}")
    if scenario == "trace2skill_promotion":
        validation_value = record.get("validation_ref") or record.get("regression_result_ref") or record.get("regression_ref")
        if validation_value not in (None, "", [], {}):
            validation_status = _resolve_trace2skill_validation_ref(validation_value, evidence_root=evidence_root)
            resolved["trace2skill_validation"] = validation_status
            if validation_status.get("status") == "unresolved":
                unresolved.append(f"trace2skill_validation:{validation_status.get('reason', 'unresolved')}")
    return {
        "schema": "yinyo.advanced_ref_resolution.v1",
        "scenario": scenario,
        "resolved": resolved,
        "unresolved": unresolved,
        "ok": not unresolved,
    }


def _resolve_advanced_ref(field: str, value: Any, *, evidence_root: Path) -> dict[str, Any]:
    if isinstance(value, dict):
        return {"status": "resolved", "kind": "inline_object", "keys": sorted(str(key) for key in value)}
    if not isinstance(value, str):
        return {"status": "resolved", "kind": "inline_value"}
    text = value.strip()
    if not text:
        return {"status": "unresolved", "reason": "empty"}
    if field == "run_id":
        return _resolve_run_id(text, evidence_root=evidence_root)
    path_candidate = _resolve_ref_path(text, evidence_root=evidence_root)
    if path_candidate is not None:
        if not path_candidate.is_file():
            return {"status": "unresolved", "kind": "path", "path": str(path_candidate), "reason": "file_missing"}
        return _resolve_ref_file(field, path_candidate)
    return {"status": "resolved", "kind": "redacted_token", "value_preview": text[:80]}


def _resolve_run_id(run_id: str, *, evidence_root: Path) -> dict[str, Any]:
    candidates = [
        evidence_root / "runs" / run_id / "manifest.json",
        evidence_root / "runs" / run_id / "handoff.json",
        evidence_root / run_id / "manifest.json",
        evidence_root / run_id / "handoff.json",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        status = _resolve_ref_file("run_id", path)
        status["run_id"] = run_id
        return status
    if re.match(r"^(r-|run-|redacted-)", run_id):
        return {"status": "resolved", "kind": "redacted_run_id", "run_id": run_id}
    return {"status": "unresolved", "kind": "run_id", "run_id": run_id, "reason": "run_artifact_missing"}


def _resolve_ref_path(value: str, *, evidence_root: Path) -> Path | None:
    looks_like_path = (
        any(sep in value for sep in ("/", "\\"))
        or value.endswith((".json", ".jsonl", ".md", ".txt"))
        or value.startswith(".")
    )
    if not looks_like_path:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = evidence_root / path
    return path.resolve()


def _resolve_ref_file(field: str, path: Path) -> dict[str, Any]:
    try:
        if path.suffix.lower() == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            schema = str(data.get("schema", "")) if isinstance(data, dict) else ""
            if field in {"validation_ref", "regression_result_ref", "regression_ref", "post_promotion_run_ref"}:
                return _validate_trace2skill_file(field, path, data)
            if field == "skill_ref":
                if isinstance(data, dict) and data.get("name"):
                    return {"status": "resolved", "kind": "skill_meta", "path": str(path), "name": data.get("name"), "schema": schema}
                return {"status": "unresolved", "kind": "skill_meta", "path": str(path), "reason": "name_missing"}
            if field == "run_id":
                if schema == "yinyo.handoff.v1" or data.get("run_id"):
                    return {"status": "resolved", "kind": "run_artifact", "path": str(path), "schema": schema, "run_id": data.get("run_id", "")}
                return {"status": "unresolved", "kind": "run_artifact", "path": str(path), "reason": "run_id_missing"}
            return {"status": "resolved", "kind": "json_file", "path": str(path), "schema": schema}
        if path.suffix.lower() == ".jsonl":
            lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            return {"status": "resolved", "kind": "jsonl_file", "path": str(path), "records": len(lines)}
        return {"status": "resolved", "kind": "file", "path": str(path), "bytes": path.stat().st_size}
    except Exception as exc:
        return {"status": "unresolved", "kind": "file", "path": str(path), "reason": f"read_failed:{type(exc).__name__}"}


def _resolve_trace2skill_validation_ref(value: Any, *, evidence_root: Path) -> dict[str, Any]:
    if not isinstance(value, str):
        return {"status": "unresolved", "reason": "validation_ref_not_string"}
    path = _resolve_ref_path(value, evidence_root=evidence_root)
    if path is None:
        return {"status": "resolved", "kind": "redacted_trace2skill_ref", "value_preview": value[:80]}
    if not path.is_file():
        return {"status": "unresolved", "kind": "trace2skill_validation", "path": str(path), "reason": "file_missing"}
    return _resolve_ref_file("validation_ref", path)


def _validate_trace2skill_file(field: str, path: Path, data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {"status": "unresolved", "kind": "trace2skill", "path": str(path), "reason": "json_object_required"}
    schema = str(data.get("schema", ""))
    if schema == "yinyo.trace2skill_validation.v1":
        checks = data.get("checks", {}) if isinstance(data.get("checks"), dict) else {}
        replay = data.get("replay_result", {}) if isinstance(data.get("replay_result"), dict) else {}
        pre_skill = data.get("pre_skill_result", {}) if isinstance(data.get("pre_skill_result"), dict) else {}
        post_skill = data.get("post_skill_result", {}) if isinstance(data.get("post_skill_result"), dict) else {}
        required_checks = (
            checks.get("pre_skill_failure_reproduced") is True
            and checks.get("post_skill_guardrail_applied") is True
            and checks.get("pre_skill_command_failed_as_expected") is True
            and checks.get("post_skill_command_passed") is True
        )
        command_evidence = (
            pre_skill.get("exit_code") not in (0, None)
            and bool(pre_skill.get("path"))
            and post_skill.get("passed") is True
            and post_skill.get("exit_code") == 0
            and bool(post_skill.get("path"))
        )
        if (
            data.get("passed") is True
            and data.get("skill_name")
            and data.get("failure_trace_ref")
            and replay.get("passed") is True
            and required_checks
            and command_evidence
        ):
            return {
                "status": "resolved",
                "kind": "trace2skill_validation",
                "path": str(path),
                "schema": schema,
                "skill_name": data.get("skill_name"),
                "replay_passed": True,
                "pre_skill_failed": True,
                "post_skill_passed": True,
            }
        return {"status": "unresolved", "kind": "trace2skill_validation", "path": str(path), "schema": schema, "reason": "validation_incomplete"}
    if schema == "yinyo.trace2skill_regression.v1":
        if (
            data.get("skill_name")
            and data.get("failure_trace_ref")
            and data.get("validation_required") is True
            and data.get("guardrail_application_required") is True
            and data.get("pre_skill_command")
            and data.get("post_skill_command")
        ):
            return {"status": "resolved", "kind": "trace2skill_regression", "path": str(path), "schema": schema, "skill_name": data.get("skill_name")}
        return {"status": "unresolved", "kind": "trace2skill_regression", "path": str(path), "schema": schema, "reason": "regression_incomplete"}
    return {"status": "unresolved", "kind": "trace2skill", "path": str(path), "schema": schema, "reason": "unsupported_schema"}


def _build_operator_plan(
    *,
    scenarios: list[dict[str, Any]],
    advanced_scenarios: list[dict[str, Any]],
    has_successful_message_job: bool,
    event_keys: set[str],
    config_path: str,
) -> list[dict[str, Any]]:
    """Build a structured handoff plan for the next smoke operator."""

    plan: list[dict[str, Any]] = []
    for item in scenarios:
        if item["ok"]:
            continue
        plan.append({
            "layer": "basic",
            "scenario": item["scenario"],
            "missing": item["missing"],
            "action": item.get("operator_action", ""),
            "command": _basic_smoke_command(item["scenario"], config_path=config_path),
        })
    for item in advanced_scenarios:
        if item["ok"]:
            continue
        plan.append({
            "layer": "advanced",
            "scenario": item["scenario"],
            "missing": item["missing"],
            "action": item.get("operator_action", ""),
            "command": _advanced_smoke_command(item["scenario"], item["missing"], config_path=config_path),
        })
    if not has_successful_message_job:
        plan.append({
            "layer": "runtime",
            "scenario": "job_store",
            "missing": ["feishu_message_succeeded"],
            "action": "Confirm at least one Feishu message job reaches status=succeeded in runtime_jobs.jsonl.",
            "command": f"yinyo smoke status --config {config_path} --json",
        })
    if not event_keys:
        plan.append({
            "layer": "runtime",
            "scenario": "event_store",
            "missing": ["seen_event_keys"],
            "action": "Confirm gateway_events.jsonl records Feishu event keys from the live smoke run.",
            "command": f"yinyo smoke status --config {config_path} --json",
        })
    return plan


def _basic_smoke_command(scenario: str, *, config_path: str) -> str:
    status = f"yinyo smoke status --config {config_path} --json"
    if scenario == "card_fallback":
        return (
            "set smoke_mode=true in the config, restart yinyo serve, send /yinyo-smoke card-fallback "
            f"in Feishu, set smoke_mode=false, restart yinyo serve, collect the remaining live scenarios, then run {status}"
        )
    if scenario == "url_verification":
        return f"configure Feishu HTTP callback URL verification while yinyo serve is running, then run {status}"
    if scenario == "duplicate_callback":
        return f"replay or resend the same Feishu event id while yinyo serve is running, then run {status}"
    if scenario == "text_message_reply":
        return f"send a plain Feishu text message to the bot while yinyo serve is running, then run {status}"
    if scenario == "image_message_reply":
        return f"send a Feishu image message to the bot while yinyo serve is running, then run {status}"
    return f"perform the live Feishu action while yinyo serve is running, then run {status}"


def _advanced_smoke_command(scenario: str, missing: list[str], *, config_path: str) -> str:
    field_hint = {
        "image_understanding": "--image-ref <redacted-image-ref>",
        "long_conversation": "--transcript-ref <redacted-transcript-ref>",
        "memory_supersession": "--memory-ref <redacted-memory-ref>",
        "trace2skill_promotion": "--failure-trace-ref <redacted-failure-trace-ref> --skill-ref <redacted-skill-ref> --regression-result-ref <redacted-validation-ref> --promotion-status proven --post-promotion-run-ref <redacted-validation-ref>",
        "deepseek_usage": "--usage-ref <redacted-usage-ref>",
        "partial_failure": "--failure-ref <redacted-failure-ref>",
    }.get(scenario, "")
    if "controlled_recorder" in missing:
        return f"rerun yinyo smoke record-advanced --config {config_path} --scenario {scenario} {field_hint}".strip()
    return f"yinyo smoke record-advanced --config {config_path} --scenario {scenario} {field_hint}".strip()


def _status_diagnostics(
    *,
    smoke_path: str,
    log_path: str,
    job_store_path: str,
    event_store_path: str,
    runtime_lock_path: str,
    transport: str,
) -> dict[str, Any]:
    try:
        from .diagnostics import summarize_runtime

        return summarize_runtime(
            log_path=log_path,
            job_store_path=job_store_path,
            smoke_evidence_path=smoke_path,
            event_store_path=event_store_path,
            runtime_lock_path=runtime_lock_path,
            transport=transport,
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _build_recovery_summary(diagnostics: dict[str, Any]) -> dict[str, Any]:
    runtime = diagnostics.get("runtime", {}) if isinstance(diagnostics.get("runtime"), dict) else {}
    jobs = diagnostics.get("jobs", {}) if isinstance(diagnostics.get("jobs"), dict) else {}
    failures = diagnostics.get("failures", {}) if isinstance(diagnostics.get("failures"), dict) else {}
    service = runtime.get("service", {}) if isinstance(runtime.get("service"), dict) else {}
    ws = runtime.get("ws", {}) if isinstance(runtime.get("ws"), dict) else {}
    job_counts = jobs.get("status_counts", {}) if isinstance(jobs.get("status_counts"), dict) else {}
    return {
        "ok": diagnostics.get("ok") is True,
        "service_last_status": service.get("last_status", "unknown"),
        "service_profile": service.get("profile", ""),
        "service_transport": service.get("transport", ""),
        "runtime_lock_status": diagnostics.get("runtime_lock", {}).get("status", "unknown")
        if isinstance(diagnostics.get("runtime_lock"), dict)
        else "unknown",
        "failed_jobs": int(job_counts.get("failed", 0) or 0),
        "abandoned_jobs": int(job_counts.get("abandoned", 0) or 0),
        "rejected_jobs": int(job_counts.get("rejected", 0) or 0),
        "dead_letter_outbox": len(failures.get("outbox_dead_letter", []) or []),
        "ack_deadline_misses": int(ws.get("ack_deadline_misses", 0) or 0),
        "webhook_rejected": len(failures.get("webhook_rejected", []) or []),
        "alerts": diagnostics.get("alerts", []) if isinstance(diagnostics.get("alerts"), list) else [],
        "error": diagnostics.get("error", ""),
    }


def _build_handoff_summary(
    *,
    ok: bool,
    operator_plan: list[dict[str, Any]],
    recovery_summary: dict[str, Any],
    frontier_readiness: dict[str, Any] | None = None,
    bundle_dir: str = "",
    bundle_digest: str = "",
    bundle_verified: bool = False,
) -> dict[str, Any]:
    blocking_layers = sorted({str(item.get("layer", "")) for item in operator_plan if item.get("layer")})
    if recovery_summary.get("alerts") or recovery_summary.get("error"):
        blocking_layers = sorted(set(blocking_layers + ["diagnostics"]))
    frontier = frontier_readiness or {}
    for item in frontier.get("operator_blockers", []) if isinstance(frontier.get("operator_blockers", []), list) else []:
        if isinstance(item, dict) and item.get("layer"):
            blocking_layers = sorted(set(blocking_layers + [str(item["layer"])]))
    return {
        "ready_to_handoff": True,
        "release_ready": ok and recovery_summary.get("ok") is True and frontier.get("ok", True) is True and not operator_plan,
        "blocking_layers": blocking_layers,
        "next_operator_commands": _dedupe([
            str(item.get("command", ""))
            for item in operator_plan
            if item.get("command")
        ]),
        "evidence_bundle_required": True,
        "bundle_dir": bundle_dir,
        "bundle_digest": bundle_digest,
        "bundle_verified": bundle_verified,
        "diagnostics_ok": recovery_summary.get("ok") is True,
        "frontier_readiness_ok": frontier.get("ok") if frontier else None,
    }


def _build_frontier_readiness(
    *,
    root: Path,
    chain: dict[str, Any],
    advanced: dict[str, Any],
    diagnostics: dict[str, Any],
    handoff_records: int,
    handoff_ready_records: int | None = None,
    bundle_verified: bool,
    require_handoff: bool = True,
) -> dict[str, Any]:
    try:
        matrix = replay_release_matrix(root / "examples" / "feishu_scenarios.json")
    except Exception as exc:
        return {
            "schema": "yinyo.frontier_readiness.v1",
            "ok": False,
            "error": str(exc),
            "operator_blockers": [{"layer": "local_matrix", "scenario": "", "missing": ["release_matrix"]}],
        }
    local_matrix = matrix.get("matrix", {}) if isinstance(matrix.get("matrix"), dict) else {}
    proof_status = local_matrix.get("proof_status", {}) if isinstance(local_matrix.get("proof_status"), dict) else {}
    harness_layers = local_matrix.get("harness_layers", {}) if isinstance(local_matrix.get("harness_layers"), dict) else {}
    advanced_passed = set(advanced.get("passed", [])) if isinstance(advanced.get("passed", []), list) else set()
    live_missing = sorted(set(chain.get("missing", [])) | {f"advanced:{name}" for name in advanced.get("missing", [])})
    ready_handoffs = handoff_records if handoff_ready_records is None else handoff_ready_records
    live_advanced = {
        "memory_supersession": "temporal_state",
        "trace2skill_promotion": "trace2skill",
        "deepseek_usage": "model_envelope",
        "partial_failure": "negative_capability",
        "long_conversation": "long_context",
        "image_understanding": "multimodal",
    }
    frontier_checks = [
        _frontier_check(
            name="ETCLOVG local layer coverage",
            layer="local_matrix",
            local_ok=harness_layers.get("ok") is True,
            live_ok=chain.get("ok") is True and advanced.get("ok") is True,
            local_refs=["yinyo.harness_layers.v1"],
            live_refs=["runtime/job/event/smoke chain", "advanced live records"],
            missing=live_missing,
        ),
        _frontier_check(
            name="TemporalTree state continuity",
            layer="advanced",
            local_ok=proof_status.get("temporal_state_recovery", {}).get("passed") is True,
            live_ok="memory_supersession" in advanced_passed,
            local_refs=["yinyo.temporal_state_report.v1"],
            live_refs=["memory_supersession"],
            missing=[] if "memory_supersession" in advanced_passed else ["advanced:memory_supersession"],
        ),
        _frontier_check(
            name="Trace-native failure diagnosis",
            layer="diagnostics",
            local_ok=proof_status.get("trace_failure_diagnosis", {}).get("passed") is True,
            live_ok=diagnostics.get("diagnosis", {}).get("schema") == "yinyo.trace_failure_diagnosis.v1",
            local_refs=["yinyo.trace_failure_diagnosis.v1"],
            live_refs=["diagnostics.diagnosis"],
            missing=[] if diagnostics.get("diagnosis", {}).get("schema") == "yinyo.trace_failure_diagnosis.v1" else ["diagnostics:trace_failure_diagnosis"],
        ),
        _frontier_check(
            name="State handoff transfer",
            layer="handoff",
            local_ok=proof_status.get("state_handoff", {}).get("passed") is True,
            live_ok=(ready_handoffs > 0) if require_handoff else True,
            local_refs=["yinyo.handoff.v1", "yinyo.handoff_resume.v1"],
            live_refs=["bundle.handoffs", "yinyo.handoff_resume.v1"],
            missing=[] if (ready_handoffs > 0 or not require_handoff) else ["bundle:handoff_ready_records"],
        ),
        _frontier_check(
            name="Adaptive simplification guard",
            layer="verification",
            local_ok=proof_status.get("adaptive_simplification", {}).get("passed") is True,
            live_ok=bundle_verified,
            local_refs=["yinyo.proof_ablation.v1"],
            live_refs=["verified bundle digest"],
            missing=[] if bundle_verified else ["bundle:verified"],
        ),
    ]
    operator_blockers = [
        {
            "layer": item["layer"],
            "scenario": item["name"],
            "missing": item["missing"],
        }
        for item in frontier_checks
        if item["ok"] is not True
    ]
    return {
        "schema": "yinyo.frontier_readiness.v1",
        "ok": local_matrix.get("ok") is True and not operator_blockers,
        "local_matrix_ok": local_matrix.get("ok") is True,
        "harness_layers_ok": harness_layers.get("ok") is True,
        "live_chain_ok": chain.get("ok") is True,
        "advanced_live_ok": advanced.get("ok") is True,
        "bundle_verified": bundle_verified,
        "handoff_records": handoff_records,
        "handoff_ready_records": ready_handoffs,
        "handoff_required": require_handoff,
        "checks": frontier_checks,
        "operator_blockers": operator_blockers,
        "live_advanced_mapping": live_advanced,
    }


def _frontier_check(
    *,
    name: str,
    layer: str,
    local_ok: bool,
    live_ok: bool,
    local_refs: list[str],
    live_refs: list[str],
    missing: list[str],
) -> dict[str, Any]:
    return {
        "name": name,
        "layer": layer,
        "ok": local_ok and live_ok,
        "local_ok": local_ok,
        "live_ok": live_ok,
        "local_refs": local_refs,
        "live_refs": live_refs,
        "missing": sorted(set(missing)),
    }


def verify_full_smoke_evidence(
    *,
    smoke_path: str,
    log_path: str,
    job_store_path: str,
    event_store_path: str,
    required: set[str] | None = None,
    transport: str = "",
) -> dict[str, Any]:
    """Verify the full 1.0 smoke gate: runtime-backed callbacks plus advanced live evidence."""
    chain = verify_smoke_evidence_chain(
        smoke_path=smoke_path,
        log_path=log_path,
        job_store_path=job_store_path,
        event_store_path=event_store_path,
        required=required,
        transport=transport,
    )
    advanced = verify_advanced_live_evidence(smoke_path)
    missing = list(chain.get("missing", []))
    missing.extend(f"advanced:{scenario}" for scenario in advanced["missing"])
    missing.extend(f"advanced_field:{field}" for field in advanced["field_missing"])
    missing.extend(f"advanced_source:{scenario}" for scenario in advanced["source_missing"])
    missing.extend(f"advanced_proof_missing:{scenario}" for scenario in advanced.get("proof_missing", []))
    missing.extend(f"advanced_proof_mismatch:{scenario}" for scenario in advanced.get("proof_mismatch", []))
    missing.extend(f"advanced_ref_unresolved:{item}" for item in advanced.get("ref_unresolved", []))
    return {
        **chain,
        "ok": chain["ok"] and advanced["ok"],
        "chain_ok": chain["ok"],
        "advanced_ok": advanced["ok"],
        "basic_chain": chain,
        "advanced": advanced,
        "missing": sorted(set(missing)),
    }


def build_live_smoke_runbook(config: Any, *, config_path: str = "./yinyo.env") -> dict[str, Any]:
    """Build an operator-facing runbook for the live Feishu 1.0 smoke."""
    smoke_path = getattr(config, "smoke_evidence_path", "") or "./workspace/smoke_evidence.jsonl"
    workspace = getattr(config, "workspace", "") or "./workspace"
    transport = getattr(config, "transport", "") or "ws"
    profile = getattr(config, "profile", "") or "local"
    log_path = getattr(config, "log_path", "") or str(Path(workspace) / "runtime.jsonl")
    job_store_path = getattr(config, "job_store_path", "") or str(Path(workspace) / "runtime_jobs.jsonl")
    event_store_path = getattr(config, "event_store_path", "") or str(Path(workspace) / "gateway_events.jsonl")
    runtime_lock_path = getattr(config, "runtime_lock_path", "") or str(Path(workspace) / "yinyo_runtime.lock")
    ws_sdk_session_id = str(getattr(config, "ws_sdk_session_id", "") or "").strip()
    ws_session_arg = ws_sdk_session_id or "<ws-session-id>"
    required_basic = required_live_smoke_scenarios(transport)
    status = build_smoke_evidence_status(
        smoke_path=smoke_path,
        log_path=log_path,
        job_store_path=job_store_path,
        event_store_path=event_store_path,
        runtime_lock_path=runtime_lock_path,
        profile=profile,
        transport=transport,
        config_path=config_path,
        required=set(required_basic),
    )
    return {
        "title": "YINYO 1.0 live smoke runbook",
        "profile": profile,
        "transport": transport,
        "workspace": workspace,
        "evidence_path": smoke_path,
        "ws_sdk_session_id": ws_sdk_session_id,
        "current_status": {
            "ok": status.get("ok") is True,
            "snapshot": status.get("snapshot", {}),
            "missing": status.get("chain", {}).get("missing", []),
            "advanced_missing": status.get("advanced", {}).get("missing", []),
            "advanced_field_missing": status.get("advanced", {}).get("field_missing", []),
            "advanced_ref_unresolved": status.get("advanced", {}).get("ref_unresolved", []),
            "next_actions": status.get("next_actions", []),
            "operator_plan": status.get("operator_plan", []),
            "recovery_summary": status.get("recovery_summary", {}),
            "frontier_readiness": status.get("frontier_readiness", {}),
            "handoff_summary": status.get("handoff_summary", {}),
        },
        "platform_setup": [
            "Use a Feishu self-built app for long-connection mode.",
            "Enable event subscription and callback long connection in Feishu.",
            "Subscribe to P2 IM message receive events.",
            "HTTP url_verification evidence is required only when transport=http.",
            "Run only one local worker against local JSONL stores during smoke.",
            "Set smoke_mode=true only for the card_fallback probe, then disable it and restart before collecting the remaining live scenarios and building the final smoke bundle.",
            "Set ws_sdk_session_id in yinyo.env before preflight; smoke bundle inherits it from config, and --ws-sdk-session-id must match if provided.",
            "Keep app secrets, verify tokens, tenant tokens, and API keys out of logs and git.",
        ],
        "commands": [
            f"yinyo serve --config {config_path} --dry-run",
            f"yinyo smoke preflight --config {config_path}",
            f"yinyo smoke reset --config {config_path} --confirm-reset",
            f"yinyo smoke plan --transport {transport} --path {smoke_path}",
            f"yinyo smoke runbook --config {config_path}",
            f"yinyo serve --config {config_path}",
            f"yinyo smoke record-advanced --config {config_path} --scenario image_understanding --image-ref <redacted-image-ref>",
            f"yinyo smoke record-advanced --config {config_path} --scenario long_conversation --transcript-ref <redacted-transcript-ref>",
            f"yinyo smoke record-advanced --config {config_path} --scenario memory_supersession --memory-ref <redacted-memory-ref>",
            f"yinyo smoke record-advanced --config {config_path} --scenario trace2skill_promotion --failure-trace-ref <redacted-failure-trace-ref> --skill-ref <redacted-skill-ref> --regression-result-ref <redacted-validation-ref> --promotion-status proven --post-promotion-run-ref <redacted-validation-ref>",
            f"yinyo smoke record-advanced --config {config_path} --scenario deepseek_usage --usage-ref <redacted-usage-ref>",
            f"yinyo smoke record-advanced --config {config_path} --scenario partial_failure --failure-ref <redacted-failure-ref>",
            f"yinyo smoke wait --config {config_path}",
            f"yinyo smoke status --config {config_path}",
            f"yinyo diagnose --config {config_path}",
            f"yinyo smoke verify --transport {transport} --path {smoke_path}",
            f"yinyo smoke bundle --config {config_path} --output {Path(smoke_path).resolve().parent / 'smoke-bundle'} --handoff-dir {Path(workspace) / 'runs'} --live-attestation-id <attestation-id> --tenant-hash <sha256-tenant> --ws-sdk-session-id {ws_session_arg}",
            f"python scripts/verify_release.py --bundle {Path(smoke_path).resolve().parent / 'smoke-bundle'}",
            "python scripts/replay_scenarios.py --matrix",
            "python scripts/verify_secrets.py",
            f"python scripts/verify_release.py --target 1.0.0 --config {config_path}",
            f"python scripts/verify_release.py --target 1.0.0 --bundle {Path(smoke_path).resolve().parent / 'smoke-bundle'} --candidate 1.0.0",
        ],
        "live_scenarios": [
            {
                "scenario": scenario,
                "operator_action": LIVE_SMOKE_SCENARIO_GUIDE[scenario],
                "required_record": {"scenario": scenario, "status": "passed", "live": True},
            }
            for scenario in sorted(REQUIRED_1_0_SCENARIOS)
            if scenario in required_basic
        ],
        "advanced_live_scenarios": [
            {
                "scenario": scenario,
                "operator_action": ADVANCED_LIVE_SCENARIO_GUIDE[scenario],
                "required_record": {"scenario": scenario, "status": "passed", "live": True},
            }
            for scenario in sorted(REQUIRED_1_0_ADVANCED_SCENARIOS)
        ],
        "local_3_6_evidence": [
            {"scenario": scenario, "evidence": detail}
            for scenario, detail in sorted(REQUIRED_3_6_LOCAL_EVIDENCE.items())
        ],
        "pass_criteria": [
            "Every required live scenario has a passed record with live=true.",
            "Every advanced 3+6 scenario has live Feishu evidence with a transcript, run, usage, memory, skill, or failure reference as required.",
            "Each smoke event_key is backed by runtime.jsonl, runtime_jobs.jsonl, and gateway_events.jsonl evidence.",
            "yinyo diagnose returns OK with no failed jobs, rejected webhooks, outbox failures, or ACK deadline misses.",
            "The only smoke record allowed before the latest service_start is card_fallback from the immediately preceding smoke_mode=true probe; collect every other basic scenario after the final smoke_mode=false restart.",
            "python scripts/replay_scenarios.py --matrix passes and covers every 3+6 product core/trait row.",
            "python scripts/verify_release.py --target 1.0.0 --config <same config> passes with the same smoke, runtime, job, and event-store paths.",
            "The same ws_sdk_session_id appears in service_start, ws_transport_start, and bundle live_provenance.ws_sdk_session_id.",
            "python scripts/verify_secrets.py passes before evidence is shared or published.",
        ],
        "redaction_rules": [
            "Do not paste raw Feishu app_secret, verify_token, tenant tokens, DeepSeek keys, or private message content.",
            "Share only redacted JSONL evidence and diagnostic summaries.",
            "If a secret appears in evidence, rotate it and follow docs/incident-playbook.md.",
        ],
    }


def format_live_smoke_runbook(runbook: dict[str, Any]) -> str:
    lines = [
        runbook["title"],
        f"profile: {runbook['profile']}",
        f"transport: {runbook['transport']}",
        f"workspace: {runbook['workspace']}",
        f"evidence_path: {runbook['evidence_path']}",
        f"ws_sdk_session_id: {runbook.get('ws_sdk_session_id', '') or '<missing>'}",
        "",
        "current status:",
        f"- ok: {runbook.get('current_status', {}).get('ok') is True}",
        f"- missing: {runbook.get('current_status', {}).get('missing', [])}",
        f"- advanced_missing: {runbook.get('current_status', {}).get('advanced_missing', [])}",
        f"- advanced_field_missing: {runbook.get('current_status', {}).get('advanced_field_missing', [])}",
        f"- advanced_ref_unresolved: {runbook.get('current_status', {}).get('advanced_ref_unresolved', [])}",
        f"- frontier_readiness: {runbook.get('current_status', {}).get('frontier_readiness', {}).get('schema', '')}",
        f"- frontier_blockers: {runbook.get('current_status', {}).get('frontier_readiness', {}).get('operator_blockers', [])}",
        f"- handoff_blocking_layers: {runbook.get('current_status', {}).get('handoff_summary', {}).get('blocking_layers', [])}",
        "",
        "platform setup:",
    ]
    lines.extend(f"- {item}" for item in runbook["platform_setup"])
    lines.extend(["", "commands:"])
    lines.extend(f"- {item}" for item in runbook["commands"])
    lines.extend(["", "live scenarios:"])
    for item in runbook["live_scenarios"]:
        lines.append(f"- {item['scenario']}: {item['operator_action']}")
    lines.extend(["", "advanced live scenarios:"])
    for item in runbook["advanced_live_scenarios"]:
        lines.append(f"- {item['scenario']}: {item['operator_action']}")
    lines.extend(["", "3+6 local evidence:"])
    for item in runbook["local_3_6_evidence"]:
        lines.append(f"- {item['scenario']}: {item['evidence']}")
    lines.extend(["", "pass criteria:"])
    lines.extend(f"- {item}" for item in runbook["pass_criteria"])
    lines.extend(["", "redaction rules:"])
    lines.extend(f"- {item}" for item in runbook["redaction_rules"])
    return "\n".join(lines)


def build_smoke_evidence_bundle(
    *,
    output_dir: str,
    smoke_path: str,
    log_path: str,
    job_store_path: str,
    event_store_path: str,
    runtime_lock_path: str = "",
    profile: str = "",
    transport: str = "",
    config_path: str = "./yinyo.env",
    handoff_dir: str = "",
    live_attestation_id: str = "",
    feishu_app_id_hash: str = "",
    tenant_hash: str = "",
    ws_sdk_session_id: str = "",
) -> dict[str, Any]:
    """Create a redacted release-evidence bundle for a live smoke run."""
    target = Path(output_dir)
    if target.exists() and not target.is_dir():
        raise ValueError(f"Bundle output path is not a directory: {output_dir}")
    target.mkdir(parents=True, exist_ok=True)

    required_basic = set(required_live_smoke_scenarios(transport))
    chain = verify_smoke_evidence_chain(
        smoke_path=smoke_path,
        log_path=log_path,
        job_store_path=job_store_path,
        event_store_path=event_store_path,
        required=required_basic,
        transport=transport,
    )
    advanced = verify_advanced_live_evidence(smoke_path)
    copied = {
        "smoke_evidence": _copy_redacted_jsonl(smoke_path, target / "smoke_evidence.redacted.jsonl"),
        "runtime_log": _copy_redacted_jsonl(log_path, target / "runtime.redacted.jsonl"),
        "job_store": _copy_redacted_jsonl(job_store_path, target / "runtime_jobs.redacted.jsonl"),
        "event_store": _copy_redacted_jsonl(event_store_path, target / "gateway_events.redacted.jsonl"),
    }
    handoff_bundle = _copy_redacted_handoff_records(handoff_dir, target / "handoffs") if handoff_dir else {
        "source": "",
        "path": "",
        "records": 0,
        "files": [],
    }

    try:
        from .diagnostics import summarize_runtime

        diagnostics = summarize_runtime(
            log_path=log_path,
            job_store_path=job_store_path,
            smoke_evidence_path=smoke_path,
            event_store_path=event_store_path,
            runtime_lock_path=runtime_lock_path or str(Path(log_path).resolve().parent / "yinyo_runtime.lock"),
            transport=transport,
        )
    except Exception as exc:
        diagnostics = {"ok": False, "error": str(exc)}

    runtime_verification = {
        "schema": "yinyo.runtime_bundle_verification.v1",
        "ok": True,
        "blockers": [],
    }
    if transport == "ws":
        runtime_blockers = _verify_ws_runtime_bundle(Path(log_path), chain)
        runtime_verification = {
            "schema": "yinyo.runtime_bundle_verification.v1",
            "ok": not runtime_blockers,
            "blockers": runtime_blockers,
        }
    live_provenance = _build_live_provenance(
        transport=transport,
        live_attestation_id=live_attestation_id,
        feishu_app_id_hash=feishu_app_id_hash,
        tenant_hash=tenant_hash,
        ws_sdk_session_id=ws_sdk_session_id,
    )
    if transport == "ws":
        runtime_binding_blockers = _verify_ws_live_provenance_runtime_binding(
            Path(log_path),
            {"live_provenance": live_provenance},
        )
        runtime_verification["blockers"].extend(runtime_binding_blockers)
        runtime_verification["ok"] = not runtime_verification["blockers"]
    live_provenance_blockers = verify_live_provenance(
        {"runtime": {"transport": transport}, "live_provenance": live_provenance},
        require_complete=False,
        prefix="bundle",
    )
    live_provenance_verification = {
        "schema": "yinyo.live_provenance_verification.v1",
        "ok": not live_provenance_blockers,
        "blockers": live_provenance_blockers,
        "complete": not verify_live_provenance(
            {"runtime": {"transport": transport}, "live_provenance": live_provenance},
            require_complete=True,
            prefix="candidate 1.0.0",
        ),
    }

    manifest = {
        "generated_at": time.time(),
        "ok": (
            chain["ok"]
            and advanced["ok"]
            and diagnostics.get("ok") is True
            and runtime_verification["ok"]
            and live_provenance_verification["ok"]
        ),
        "runtime": {
            "profile": profile,
            "transport": transport,
        },
        "chain": chain,
        "correlation": chain.get("correlation", {}),
        "advanced": advanced,
        "advanced_ref_attestation": _build_advanced_ref_attestation(advanced, smoke_path=smoke_path),
        "diagnostics": diagnostics,
        "runtime_verification": runtime_verification,
        "files": copied,
        "handoffs": handoff_bundle,
        "live_provenance": live_provenance,
        "live_provenance_verification": live_provenance_verification,
        "redaction": {
            "applied": True,
            "note": "Source JSONL files are copied through redact_secrets before being written to this bundle.",
        },
    }
    status = build_smoke_evidence_status(
        smoke_path=smoke_path,
        log_path=log_path,
        job_store_path=job_store_path,
        event_store_path=event_store_path,
        runtime_lock_path=runtime_lock_path,
        profile=profile,
        transport=transport,
        config_path=config_path,
        required=required_basic,
    )
    manifest["operator_next_actions"] = status["next_actions"]
    manifest["operator_plan"] = status["operator_plan"]
    manifest["recovery_summary"] = status["recovery_summary"]
    handoff_records = int(handoff_bundle.get("records", 0) or 0) if isinstance(handoff_bundle, dict) else 0
    handoff_ready_records = int(handoff_bundle.get("ready_records", 0) or 0) if isinstance(handoff_bundle, dict) else 0
    manifest["frontier_readiness"] = _build_frontier_readiness(
        root=Path(__file__).resolve().parents[1],
        chain=chain,
        advanced=advanced,
        diagnostics=diagnostics,
        handoff_records=handoff_records,
        handoff_ready_records=handoff_ready_records,
        bundle_verified=False,
        require_handoff=transport == "ws",
    )
    manifest["handoff_summary"] = status["handoff_summary"]
    _write_json(target / "chain.json", chain)
    _write_json(target / "advanced.json", advanced)
    _write_json(target / "diagnostics.json", diagnostics)
    manifest["file_hashes"] = _bundle_file_hashes(target, copied, handoff_bundle)
    manifest["bundle_digest"] = _bundle_digest(manifest["file_hashes"])
    manifest["frontier_readiness"] = _build_frontier_readiness(
        root=Path(__file__).resolve().parents[1],
        chain=chain,
        advanced=advanced,
        diagnostics=diagnostics,
        handoff_records=handoff_records,
        handoff_ready_records=handoff_ready_records,
        bundle_verified=manifest["ok"],
        require_handoff=transport == "ws",
    )
    manifest["ok"] = manifest["ok"] and manifest["frontier_readiness"].get("ok") is True
    if manifest["frontier_readiness"].get("bundle_verified") is not manifest["ok"]:
        manifest["frontier_readiness"] = _build_frontier_readiness(
            root=Path(__file__).resolve().parents[1],
            chain=chain,
            advanced=advanced,
            diagnostics=diagnostics,
            handoff_records=handoff_records,
            handoff_ready_records=handoff_ready_records,
            bundle_verified=manifest["ok"],
            require_handoff=transport == "ws",
        )
        manifest["ok"] = manifest["ok"] and manifest["frontier_readiness"].get("ok") is True
    manifest["handoff_summary"] = _build_handoff_summary(
        ok=manifest["ok"],
        operator_plan=manifest["operator_plan"],
        recovery_summary=manifest["recovery_summary"],
        frontier_readiness=manifest["frontier_readiness"],
        bundle_dir=str(target),
        bundle_digest=manifest["bundle_digest"],
        bundle_verified=manifest["ok"],
    )
    _write_json(target / "manifest.json", manifest)
    return manifest


def verify_smoke_evidence_bundle(bundle_dir: str, require_run_handoff: bool = False) -> dict[str, Any]:
    """Verify a redacted smoke evidence bundle without reading raw runtime files."""
    target = Path(bundle_dir)
    required = {
        "manifest": target / "manifest.json",
        "chain": target / "chain.json",
        "diagnostics": target / "diagnostics.json",
        "advanced": target / "advanced.json",
        "smoke_evidence": target / "smoke_evidence.redacted.jsonl",
        "runtime_log": target / "runtime.redacted.jsonl",
        "job_store": target / "runtime_jobs.redacted.jsonl",
        "event_store": target / "gateway_events.redacted.jsonl",
    }
    missing = [name for name, path in required.items() if not path.is_file()]
    blockers = [f"missing bundle file: {name}" for name in missing]
    manifest: dict[str, Any] = {}
    chain: dict[str, Any] = {}
    diagnostics: dict[str, Any] = {}
    advanced: dict[str, Any] = {}
    if not missing:
        try:
            manifest = json.loads(required["manifest"].read_text(encoding="utf-8"))
            chain = json.loads(required["chain"].read_text(encoding="utf-8"))
            diagnostics = json.loads(required["diagnostics"].read_text(encoding="utf-8"))
            advanced = json.loads(required["advanced"].read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            blockers.append(f"invalid bundle json: {exc}")
    if manifest:
        if manifest.get("ok") is not True:
            blockers.append("bundle manifest ok is not true")
        runtime = manifest.get("runtime", {})
        if not isinstance(runtime, dict) or not runtime.get("transport"):
            blockers.append("bundle runtime transport missing")
        if runtime.get("transport") == "ws":
            ws_blockers = _verify_ws_runtime_bundle(required["runtime_log"], manifest.get("chain", {}))
            runtime_binding_blockers = _verify_ws_live_provenance_runtime_binding(required["runtime_log"], manifest)
            runtime_blockers = ws_blockers + runtime_binding_blockers
            blockers.extend(runtime_blockers)
            runtime_verification = manifest.get("runtime_verification", {})
            if not isinstance(runtime_verification, dict) or runtime_verification.get("schema") != "yinyo.runtime_bundle_verification.v1":
                blockers.append("bundle runtime verification metadata invalid")
            else:
                runtime_ok = not runtime_blockers
                if runtime_verification.get("ok") is not runtime_ok:
                    blockers.append("bundle runtime verification does not match redacted runtime log")
                if sorted(runtime_verification.get("blockers", [])) != sorted(runtime_blockers):
                    blockers.append("bundle runtime verification blockers do not match redacted runtime log")
        if manifest.get("redaction", {}).get("applied") is not True:
            blockers.append("bundle redaction marker missing")
        frontier_blockers = _verify_bundle_frontier_readiness(manifest, require_live=manifest.get("ok") is True)
        blockers.extend(frontier_blockers)
        ref_attestation_blockers = _verify_bundle_advanced_ref_attestation(manifest, advanced)
        blockers.extend(ref_attestation_blockers)
        provenance_blockers = _verify_bundle_live_provenance(manifest, require_complete=False)
        blockers.extend(provenance_blockers)
        provenance_verification = manifest.get("live_provenance_verification", {})
        if not isinstance(provenance_verification, dict) or provenance_verification.get("schema") != "yinyo.live_provenance_verification.v1":
            blockers.append("bundle live provenance verification metadata invalid")
        else:
            provenance_ok = not provenance_blockers
            provenance_complete = not _verify_bundle_live_provenance(manifest, require_complete=True, prefix="candidate 1.0.0")
            if provenance_verification.get("ok") is not provenance_ok:
                blockers.append("bundle live provenance verification does not match manifest provenance")
            if sorted(provenance_verification.get("blockers", [])) != sorted(provenance_blockers):
                blockers.append("bundle live provenance verification blockers do not match manifest provenance")
            if provenance_verification.get("complete") is not provenance_complete:
                blockers.append("bundle live provenance verification completeness does not match manifest provenance")
        hash_blockers = _verify_bundle_file_hashes(target, required, manifest)
        blockers.extend(hash_blockers)
        digest_blockers = _verify_bundle_digest(manifest)
        blockers.extend(digest_blockers)
        if manifest.get("chain", {}).get("ok") != chain.get("ok"):
            blockers.append("bundle chain mismatch")
        if manifest.get("diagnostics", {}).get("ok") != diagnostics.get("ok"):
            blockers.append("bundle diagnostics mismatch")
        if manifest.get("advanced", {}).get("ok") != advanced.get("ok"):
            blockers.append("bundle advanced evidence mismatch")
        if manifest.get("correlation", {}).get("ok") != manifest.get("chain", {}).get("correlation", {}).get("ok"):
            blockers.append("bundle correlation mismatch")
        handoff_blockers = _verify_bundle_handoffs(target, manifest)
        blockers.extend(handoff_blockers)
        if require_run_handoff and runtime.get("transport") == "ws" and manifest.get("handoffs", {}).get("records", 0) < 1:
            blockers.append("bundle run-level handoff.json missing")
        if require_run_handoff and runtime.get("transport") == "ws" and manifest.get("handoffs", {}).get("ready_records", 0) < 1:
            blockers.append("bundle replayable run-level handoff missing")
    recalculated_chain: dict[str, Any] = {}
    if not missing:
        runtime_transport = str(manifest.get("runtime", {}).get("transport", ""))
        required_basic = set(required_live_smoke_scenarios(runtime_transport))
        recalculated_chain = verify_smoke_evidence_chain(
            smoke_path=str(required["smoke_evidence"]),
            log_path=str(required["runtime_log"]),
            job_store_path=str(required["job_store"]),
            event_store_path=str(required["event_store"]),
            required=required_basic,
            transport=runtime_transport,
        )
        if recalculated_chain.get("ok") is not True:
            blockers.append(f"bundle redacted chain incomplete: {recalculated_chain.get('missing', [])}")
        if recalculated_chain.get("correlation", {}).get("ok") is not True:
            blockers.append(f"bundle redacted correlation incomplete: {recalculated_chain.get('correlation', {}).get('missing', [])}")
        if chain and sorted(chain.get("missing", [])) != sorted(recalculated_chain.get("missing", [])):
            blockers.append("bundle chain does not match redacted JSONL")
        if manifest and sorted(manifest.get("correlation", {}).get("missing", [])) != sorted(recalculated_chain.get("correlation", {}).get("missing", [])):
            blockers.append("bundle correlation does not match redacted JSONL")
        recalculated_advanced = verify_advanced_live_evidence(str(required["smoke_evidence"]), resolve_refs=False)
        if recalculated_advanced.get("ok") is not True:
            blockers.append(
                f"bundle advanced evidence incomplete: missing={recalculated_advanced.get('missing', [])}, fields={recalculated_advanced.get('field_missing', [])}, sources={recalculated_advanced.get('source_missing', [])}, proof_missing={recalculated_advanced.get('proof_missing', [])}, proof_mismatch={recalculated_advanced.get('proof_mismatch', [])}, ref_unresolved={recalculated_advanced.get('ref_unresolved', [])}"
            )
        if advanced and (
            sorted(advanced.get("passed", [])) != sorted(recalculated_advanced.get("passed", []))
            or sorted(advanced.get("missing", [])) != sorted(recalculated_advanced.get("missing", []))
            or sorted(advanced.get("field_missing", [])) != sorted(recalculated_advanced.get("field_missing", []))
            or sorted(advanced.get("source_missing", [])) != sorted(recalculated_advanced.get("source_missing", []))
            or sorted(advanced.get("proof_missing", [])) != sorted(recalculated_advanced.get("proof_missing", []))
            or sorted(advanced.get("proof_mismatch", [])) != sorted(recalculated_advanced.get("proof_mismatch", []))
        ):
            blockers.append("bundle advanced evidence does not match redacted JSONL")
        recalculated_attestation_blockers = _verify_bundle_advanced_ref_attestation(manifest, recalculated_advanced)
        if recalculated_attestation_blockers:
            blockers.append(
                "bundle advanced ref attestation does not match redacted JSONL: "
                + ", ".join(recalculated_attestation_blockers)
            )
    if chain and chain.get("ok") is not True:
        blockers.append(f"bundle chain incomplete: {chain.get('missing', [])}")
    if advanced and advanced.get("ok") is not True:
        blockers.append(
            f"bundle advanced evidence incomplete: {advanced.get('missing', []) + advanced.get('field_missing', []) + advanced.get('source_missing', []) + advanced.get('proof_missing', []) + advanced.get('proof_mismatch', []) + advanced.get('ref_unresolved', [])}"
        )
    if diagnostics and diagnostics.get("ok") is not True:
        blockers.append(f"bundle diagnostics not ok: {diagnostics.get('alerts', diagnostics.get('error', []))}")
    secret_hits = _scan_bundle_for_secrets(target)
    blockers.extend(secret_hits)
    return {
        "ok": not blockers,
        "bundle_dir": str(target),
        "files": {name: str(path) for name, path in required.items()},
        "blockers": blockers,
        "manifest": {
            "generated_at": manifest.get("generated_at", ""),
            "ok": manifest.get("ok"),
            "runtime": manifest.get("runtime", {}),
            "redaction": manifest.get("redaction", {}),
            "file_hashes": manifest.get("file_hashes", {}),
            "bundle_digest": manifest.get("bundle_digest", ""),
            "correlation": manifest.get("correlation", {}),
            "handoffs": manifest.get("handoffs", {}),
            "frontier_readiness": manifest.get("frontier_readiness", {}),
            "runtime_verification": manifest.get("runtime_verification", {}),
            "live_provenance": manifest.get("live_provenance", {}),
            "live_provenance_verification": manifest.get("live_provenance_verification", {}),
            "advanced_ref_attestation": manifest.get("advanced_ref_attestation", {}),
        } if manifest else {},
        "chain_ok": chain.get("ok") if chain else None,
        "redacted_chain_ok": recalculated_chain.get("ok") if recalculated_chain else None,
        "diagnostics_ok": diagnostics.get("ok") if diagnostics else None,
        "advanced_ok": advanced.get("ok") if advanced else None,
}


def _build_live_provenance(
    *,
    transport: str,
    live_attestation_id: str = "",
    feishu_app_id_hash: str = "",
    tenant_hash: str = "",
    ws_sdk_session_id: str = "",
) -> dict[str, Any]:
    return {
        "schema": "yinyo.live_provenance.v1",
        "generated_at": time.time(),
        "transport": transport,
        "operator_attestation_id": live_attestation_id.strip(),
        "feishu_app_id_hash": feishu_app_id_hash.strip(),
        "tenant_hash": tenant_hash.strip(),
        "ws_sdk_session_id": ws_sdk_session_id.strip(),
        "note": "Redacted operator-supplied proof that this bundle came from a real live Feishu smoke run.",
    }


def verify_live_provenance(manifest: dict[str, Any], *, require_complete: bool = True, prefix: str = "candidate 1.0.0") -> list[str]:
    return _verify_bundle_live_provenance(manifest, require_complete=require_complete, prefix=prefix)


def _verify_bundle_live_provenance(
    manifest: dict[str, Any],
    *,
    require_complete: bool,
    prefix: str = "bundle",
) -> list[str]:
    provenance = manifest.get("live_provenance", {})
    if not isinstance(provenance, dict) or provenance.get("schema") != "yinyo.live_provenance.v1":
        return [f"{prefix} requires live provenance attestation"] if require_complete else []
    transport = manifest.get("runtime", {}).get("transport", "")
    required = [
        "operator_attestation_id",
        "feishu_app_id_hash",
        "tenant_hash",
    ]
    if transport == "ws":
        required.append("ws_sdk_session_id")
    missing = [name for name in required if not str(provenance.get(name, "")).strip()]
    if require_complete and missing:
        return [f"{prefix} requires live provenance fields: {', '.join(missing)}"]
    present_required = [name for name in required if str(provenance.get(name, "")).strip()]
    invalid = [
        name
        for name in present_required
        if _is_placeholder_provenance(provenance.get(name, ""))
    ]
    malformed_hashes = [
        name
        for name in ("feishu_app_id_hash", "tenant_hash")
        if name in present_required and not _looks_like_sha256(provenance.get(name, ""))
    ]
    if invalid:
        return [f"{prefix} rejects placeholder live provenance fields: {', '.join(invalid)}"]
    if malformed_hashes:
        return [f"{prefix} requires sha256 live provenance hashes: {', '.join(malformed_hashes)}"]
    return []


def _is_placeholder_provenance(value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    lowered = text.lower()
    if lowered.startswith("<") and lowered.endswith(">"):
        return True
    placeholder_tokens = {
        "placeholder",
        "redacted",
        "example",
        "fake",
        "synthetic",
        "fixture",
        "local",
        "test",
        "todo",
        "none",
        "null",
    }
    parts = [part for part in re.split(r"[^a-z0-9]+", lowered) if part]
    return any(part in placeholder_tokens for part in parts)


def _looks_like_sha256(value: object) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F]{64}", str(value or "").strip()))


def _build_advanced_ref_attestation(advanced: dict[str, Any], *, smoke_path: str = "") -> dict[str, Any]:
    ref_status = advanced.get("ref_status", {}) if isinstance(advanced, dict) else {}
    records = load_smoke_evidence(smoke_path) if smoke_path else []
    latest = {
        str(item.get("scenario", "")): item
        for item in records
        if item.get("status") == "passed" and item.get("live") is True
    }
    scenarios: dict[str, Any] = {}
    for scenario in sorted(advanced.get("passed", []) if isinstance(advanced, dict) else []):
        status = ref_status.get(scenario, {}) if isinstance(ref_status, dict) else {}
        resolved = status.get("resolved", {}) if isinstance(status, dict) and isinstance(status.get("resolved"), dict) else {}
        proof = latest.get(scenario, {}).get("advanced_proof", {})
        if not isinstance(proof, dict):
            proof = {}
        scenarios[scenario] = {
            "schema": "yinyo.advanced_ref_attestation.scenario.v1",
            "scenario": scenario,
            "ok": status.get("ok") is True if isinstance(status, dict) else False,
            "ref_resolution_schema": status.get("schema", "") if isinstance(status, dict) else "",
            "ref_resolution_mode": status.get("mode", "") if isinstance(status, dict) else "",
            "refs": sorted(str(key) for key in resolved if str(key) != "trace2skill_validation"),
            "unresolved": status.get("unresolved", []) if isinstance(status, dict) and isinstance(status.get("unresolved"), list) else [],
            "resolved_kinds": {
                str(field): str(item.get("kind", item.get("status", ""))) if isinstance(item, dict) else ""
                for field, item in sorted(resolved.items())
            },
            "proof_schema": proof.get("schema", ""),
            "proof_digest": proof.get("digest", ""),
            "proof_refs": proof.get("refs", []),
        }
    blockers = []
    required = set(REQUIRED_1_0_ADVANCED_SCENARIOS)
    missing = sorted(required - set(scenarios))
    if missing:
        blockers.extend(f"missing:{scenario}" for scenario in missing)
    for scenario, item in scenarios.items():
        if item["ok"] is not True:
            blockers.append(f"ref_status:{scenario}")
        if item["ref_resolution_schema"] != "yinyo.advanced_ref_resolution.v1":
            blockers.append(f"ref_schema:{scenario}")
        if item["unresolved"]:
            blockers.append(f"unresolved:{scenario}")
        if item["proof_schema"] != ADVANCED_LIVE_PROOF_SCHEMA or not item["proof_digest"]:
            blockers.append(f"proof:{scenario}")
    payload = {
        "schema": "yinyo.advanced_ref_attestation.v1",
        "scenarios": scenarios,
        "blockers": blockers,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["digest"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    payload["ok"] = not blockers
    return payload


def _verify_bundle_frontier_readiness(manifest: dict[str, Any], *, require_live: bool = False) -> list[str]:
    frontier = manifest.get("frontier_readiness", {})
    if not isinstance(frontier, dict):
        return ["bundle frontier readiness metadata invalid"]
    blockers: list[str] = []
    handoffs = manifest.get("handoffs", {}) if isinstance(manifest.get("handoffs", {}), dict) else {}
    handoff_records = int(handoffs.get("records", 0) or 0)
    handoff_ready_records = int(handoffs.get("ready_records", 0) or 0)
    if frontier.get("schema") != "yinyo.frontier_readiness.v1":
        blockers.append("bundle frontier readiness schema invalid")
    if frontier.get("ok") is not True:
        blockers.append("bundle frontier readiness is not true")
    if frontier.get("handoff_records") != handoff_records:
        blockers.append("bundle frontier handoff_records mismatch")
    if frontier.get("handoff_ready_records") != handoff_ready_records:
        blockers.append("bundle frontier handoff_ready_records mismatch")
    handoff_required = frontier.get("handoff_required") is True
    required_checks = {
        "ETCLOVG local layer coverage",
        "TemporalTree state continuity",
        "Trace-native failure diagnosis",
        "State handoff transfer",
        "Adaptive simplification guard",
    }
    checks = frontier.get("checks", [])
    if not isinstance(checks, list):
        blockers.append("bundle frontier readiness checks invalid")
        checks = []
    seen = {str(item.get("name", "")) for item in checks if isinstance(item, dict)}
    missing = sorted(required_checks - seen)
    if missing:
        blockers.append(f"bundle frontier readiness checks missing: {missing}")
    for item in checks:
        if not isinstance(item, dict):
            blockers.append("bundle frontier readiness check invalid")
            continue
        if item.get("name") in required_checks and item.get("local_ok") is not True:
            blockers.append(f"bundle frontier local proof failed: {item.get('name')}")
        if (
            require_live
            and item.get("name") in required_checks
            and not (item.get("name") == "State handoff transfer" and not handoff_required)
            and item.get("live_ok") is not True
        ):
            blockers.append(f"bundle frontier live proof failed: {item.get('name')}")
        if item.get("name") == "State handoff transfer":
            if handoff_required:
                expected_live_ok = handoff_ready_records > 0
                if item.get("live_ok") is not expected_live_ok:
                    blockers.append("bundle frontier handoff live proof mismatch")
                missing = item.get("missing", [])
                if handoff_ready_records <= 0 and "bundle:handoff_ready_records" not in missing:
                    blockers.append("bundle frontier handoff missing marker mismatch")
                if handoff_ready_records > 0 and missing:
                    blockers.append("bundle frontier handoff missing marker mismatch")
    return blockers


def _verify_bundle_advanced_ref_attestation(manifest: dict[str, Any], advanced: dict[str, Any]) -> list[str]:
    attestation = manifest.get("advanced_ref_attestation", {})
    if not isinstance(attestation, dict) or attestation.get("schema") != "yinyo.advanced_ref_attestation.v1":
        return ["bundle advanced ref attestation missing"]
    scenarios = attestation.get("scenarios", {})
    if not isinstance(scenarios, dict):
        return ["bundle advanced ref attestation scenarios invalid"]
    blockers: list[str] = []
    expected = set(advanced.get("passed", [])) if isinstance(advanced, dict) else set()
    missing = sorted(expected - set(scenarios))
    if missing:
        blockers.append(f"bundle advanced ref attestation missing scenarios: {missing}")
    if attestation.get("ok") is not True:
        blockers.append(f"bundle advanced ref attestation is not true: {attestation.get('blockers', [])}")
    digest = attestation.get("digest")
    if not isinstance(digest, str) or len(digest) != 64:
        blockers.append("bundle advanced ref attestation digest missing")
    else:
        payload = {
            "schema": attestation.get("schema"),
            "scenarios": scenarios,
            "blockers": attestation.get("blockers", []),
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != digest:
            blockers.append("bundle advanced ref attestation digest mismatch")
    for scenario in sorted(expected):
        item = scenarios.get(scenario, {})
        if not isinstance(item, dict):
            blockers.append(f"bundle advanced ref attestation scenario invalid: {scenario}")
            continue
        if item.get("schema") != "yinyo.advanced_ref_attestation.scenario.v1":
            blockers.append(f"bundle advanced ref attestation scenario schema invalid: {scenario}")
        if item.get("ok") is not True:
            blockers.append(f"bundle advanced ref attestation scenario not ok: {scenario}")
        if item.get("ref_resolution_schema") != "yinyo.advanced_ref_resolution.v1":
            blockers.append(f"bundle advanced ref attestation ref schema invalid: {scenario}")
        if item.get("ref_resolution_mode") == "skipped_for_redacted_bundle":
            blockers.append(f"bundle advanced ref attestation was built from redacted refs: {scenario}")
        if item.get("unresolved"):
            blockers.append(f"bundle advanced ref attestation unresolved refs: {scenario}")
        refs = item.get("refs", [])
        proof_refs = item.get("proof_refs", [])
        if not isinstance(refs, list):
            blockers.append(f"bundle advanced ref attestation refs invalid: {scenario}")
            refs = []
        if not isinstance(proof_refs, list) or not proof_refs:
            blockers.append(f"bundle advanced ref attestation proof refs missing: {scenario}")
        if item.get("proof_schema") != ADVANCED_LIVE_PROOF_SCHEMA or not item.get("proof_digest"):
            blockers.append(f"bundle advanced ref attestation proof missing: {scenario}")
    return blockers


def reset_smoke_evidence_files(
    *,
    smoke_path: str,
    log_path: str,
    job_store_path: str,
    event_store_path: str,
    confirm: bool = False,
) -> dict[str, Any]:
    """Clear runtime evidence files before a fresh live smoke run."""

    if not confirm:
        raise ValueError("reset requires confirm=True")
    paths = {
        "smoke_evidence": smoke_path,
        "runtime_log": log_path,
        "job_store": job_store_path,
        "event_store": event_store_path,
    }
    reset = {}
    for name, raw_path in paths.items():
        path = Path(raw_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        existed = path.exists()
        previous_bytes = path.stat().st_size if existed else 0
        path.write_text("", encoding="utf-8")
        reset[name] = {
            "path": str(path),
            "existed": existed,
            "previous_bytes": previous_bytes,
            "bytes": path.stat().st_size,
        }
    return {"ok": True, "reset": reset}


def _load_jsonl(path: str) -> list[dict[str, Any]]:
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


def _copy_redacted_jsonl(source: str, target: Path) -> dict[str, Any]:
    records = _load_jsonl(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as f:
        for item in records:
            text = json.dumps(_redact_sensitive_fields(item), ensure_ascii=False)
            f.write(redact_secrets(text) + "\n")
    return {
        "source": source,
        "path": str(target),
        "records": len(records),
    }


def _copy_redacted_handoff_records(source_dir: str, target_dir: Path) -> dict[str, Any]:
    from .handoff import replay_handoff

    source = Path(source_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    ready_records = 0
    if not source.is_dir():
        return {
            "source": source_dir,
            "path": str(target_dir),
            "records": 0,
            "ready_records": 0,
            "files": [],
            "artifacts": [],
            "missing": True,
        }
    for path in sorted(source.rglob("handoff.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        run_id = str(data.get("run_id") or path.parent.name or f"handoff-{len(files) + 1}")
        run_name = _safe_bundle_name(run_id)
        run_target_dir = target_dir / run_name
        run_target_dir.mkdir(parents=True, exist_ok=True)
        artifacts_map = data.get("artifacts", {}) if isinstance(data.get("artifacts"), dict) else {}
        for artifact_key in ("evidence_file", "manifest_file"):
            artifact_source = _resolve_handoff_artifact_source(source, path, artifacts_map.get(artifact_key, ""))
            artifact_target = run_target_dir / Path(str(artifacts_map.get(artifact_key, artifact_key))).name
            if artifact_source.is_file():
                if artifact_source.suffix.lower() == ".jsonl":
                    _copy_redacted_jsonl(str(artifact_source), artifact_target)
                else:
                    try:
                        artifact_data = json.loads(artifact_source.read_text(encoding="utf-8"))
                        _write_json(artifact_target, artifact_data if isinstance(artifact_data, dict) else {"value": artifact_data})
                    except (OSError, json.JSONDecodeError):
                        try:
                            artifact_target.write_text(redact_secrets(artifact_source.read_text(encoding="utf-8")), encoding="utf-8")
                        except OSError:
                            continue
                data.setdefault("artifacts", {})[artifact_key] = str(artifact_target.relative_to(target_dir.parent)).replace("\\", "/")
                artifacts.append({
                    "run_id": run_id,
                    "key": artifact_key,
                    "source": str(artifact_source),
                    "path": str(artifact_target),
                })
        target = target_dir / f"{_safe_bundle_name(run_id)}.handoff.json"
        _write_json(target, data)
        resume = replay_handoff(target, workspace=target_dir.parent)
        replay_ok = resume.get("ok") is True
        if replay_ok:
            ready_records += 1
        files.append({
            "run_id": run_id,
            "source": str(path),
            "path": str(target),
            "schema": data.get("schema", ""),
            "replay_ok": replay_ok,
            "replay_blockers": resume.get("blockers", []),
        })
    return {
        "source": source_dir,
        "path": str(target_dir),
        "records": len(files),
        "ready_records": ready_records,
        "files": files,
        "artifacts": artifacts,
    }


def _resolve_handoff_artifact_source(source_root: Path, handoff_path: Path, value: Any) -> Path:
    text = str(value or "")
    if not text:
        return source_root / "__missing__"
    path = Path(text)
    if path.is_absolute():
        return path
    candidates = [
        source_root / path,
        source_root.parent / path,
        handoff_path.parent / path.name,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def _safe_bundle_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip(".-")
    return cleaned[:120] or "handoff"


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(redact_secrets(json.dumps(_redact_sensitive_fields(data), ensure_ascii=False, indent=2)), encoding="utf-8")


def _bundle_file_hashes(target: Path, copied: dict[str, dict[str, Any]], handoffs: dict[str, Any] | None = None) -> dict[str, str]:
    files = {
        "chain": target / "chain.json",
        "advanced": target / "advanced.json",
        "diagnostics": target / "diagnostics.json",
    }
    for name, item in copied.items():
        files[name] = Path(str(item.get("path", "")))
    for item in (handoffs or {}).get("files", []) if isinstance(handoffs, dict) else []:
        if not isinstance(item, dict):
            continue
        run_id = _safe_bundle_name(str(item.get("run_id", "")))
        files[f"handoff:{run_id}"] = Path(str(item.get("path", "")))
    for item in (handoffs or {}).get("artifacts", []) if isinstance(handoffs, dict) else []:
        if not isinstance(item, dict):
            continue
        run_id = _safe_bundle_name(str(item.get("run_id", "")))
        key = _safe_bundle_name(str(item.get("key", "")))
        files[f"handoff_artifact:{run_id}:{key}"] = Path(str(item.get("path", "")))
    return {name: _sha256_file(path) for name, path in sorted(files.items())}


def _bundle_digest(file_hashes: dict[str, str]) -> str:
    payload = json.dumps(file_hashes, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _build_advanced_live_proof(scenario: str, record: dict[str, Any]) -> dict[str, Any]:
    refs = _advanced_live_proof_refs(scenario, record)
    payload = {
        "schema": ADVANCED_LIVE_PROOF_SCHEMA,
        "scenario": scenario,
        "refs": refs,
        "fields": {ref: _redact_sensitive_fields(_redact_value(record.get(ref))) for ref in refs},
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "schema": ADVANCED_LIVE_PROOF_SCHEMA,
        "scenario": scenario,
        "refs": refs,
        "digest": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }


def _advanced_live_proof_refs(scenario: str, record: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for alternatives in ADVANCED_LIVE_REQUIRED_FIELDS.get(scenario, ()):
        for field in alternatives:
            if record.get(field) not in (None, "", [], {}):
                refs.append(field)
                break
    return sorted(refs)


def _verify_bundle_digest(manifest: dict[str, Any]) -> list[str]:
    hashes = manifest.get("file_hashes", {})
    digest = manifest.get("bundle_digest")
    if not isinstance(hashes, dict) or not hashes:
        return []
    if not isinstance(digest, str) or not digest:
        return ["bundle digest missing"]
    if digest != _bundle_digest(hashes):
        return ["bundle digest mismatch"]
    return []


def _verify_bundle_file_hashes(target: Path, required: dict[str, Path], manifest: dict[str, Any]) -> list[str]:
    hashes = manifest.get("file_hashes", {})
    expected_names = {"chain", "advanced", "diagnostics", "smoke_evidence", "runtime_log", "job_store", "event_store"}
    handoffs = manifest.get("handoffs", {})
    if isinstance(handoffs, dict):
        for item in handoffs.get("files", []):
            if isinstance(item, dict):
                expected_names.add(f"handoff:{_safe_bundle_name(str(item.get('run_id', '')))}")
        for item in handoffs.get("artifacts", []):
            if isinstance(item, dict):
                expected_names.add(
                    f"handoff_artifact:{_safe_bundle_name(str(item.get('run_id', '')))}:{_safe_bundle_name(str(item.get('key', '')))}"
                )
    if not isinstance(hashes, dict):
        return ["bundle file hashes missing"]
    blockers = []
    missing_names = sorted(expected_names - set(hashes))
    if missing_names:
        blockers.append(f"bundle file hashes missing: {missing_names}")
    hash_paths = {
        "chain": required["chain"],
        "advanced": required["advanced"],
        "diagnostics": required["diagnostics"],
        "smoke_evidence": required["smoke_evidence"],
        "runtime_log": required["runtime_log"],
        "job_store": required["job_store"],
        "event_store": required["event_store"],
    }
    if isinstance(handoffs, dict):
        for item in handoffs.get("files", []):
            if isinstance(item, dict):
                hash_paths[f"handoff:{_safe_bundle_name(str(item.get('run_id', '')))}"] = Path(str(item.get("path", "")))
        for item in handoffs.get("artifacts", []):
            if isinstance(item, dict):
                hash_paths[
                    f"handoff_artifact:{_safe_bundle_name(str(item.get('run_id', '')))}:{_safe_bundle_name(str(item.get('key', '')))}"
                ] = Path(str(item.get("path", "")))
    for name, path in hash_paths.items():
        if name not in hashes or not path.is_file():
            continue
        actual = _sha256_file(path)
        if hashes.get(name) != actual:
            blockers.append(f"bundle file hash mismatch: {name}")
    return blockers


def _verify_bundle_handoffs(target: Path, manifest: dict[str, Any]) -> list[str]:
    from .handoff import replay_handoff

    handoffs = manifest.get("handoffs", {})
    if not handoffs:
        return []
    if not isinstance(handoffs, dict):
        return ["bundle handoffs metadata invalid"]
    if handoffs.get("missing") is True:
        return ["bundle handoff source missing"]
    files = handoffs.get("files", [])
    records = handoffs.get("records", 0)
    if records and not files:
        return ["bundle handoff file list missing"]
    blockers: list[str] = []
    ready_records = 0
    artifact_entries = handoffs.get("artifacts", [])
    if artifact_entries and not isinstance(artifact_entries, list):
        blockers.append("bundle handoff artifact metadata invalid")
        artifact_entries = []
    artifact_keys = {
        (str(item.get("run_id", "")), str(item.get("key", "")))
        for item in artifact_entries
        if isinstance(item, dict)
    }
    for item in files:
        if not isinstance(item, dict):
            blockers.append("bundle handoff entry invalid")
            continue
        path = Path(str(item.get("path", "")))
        try:
            path.relative_to(target)
        except ValueError:
            blockers.append("bundle handoff path outside bundle")
        if not path.is_file():
            blockers.append(f"bundle handoff file missing: {item.get('run_id', '')}")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            blockers.append(f"bundle handoff json invalid: {exc}")
            continue
        if data.get("schema") != "yinyo.handoff.v1":
            blockers.append(f"bundle handoff schema invalid: {item.get('run_id', '')}")
        if not data.get("run_id"):
            blockers.append("bundle handoff run_id missing")
        artifacts = data.get("artifacts", {})
        provenance = data.get("provenance", {})
        if not isinstance(artifacts, dict) or not artifacts.get("evidence_file"):
            blockers.append(f"bundle handoff evidence_file missing: {item.get('run_id', '')}")
        elif (str(data.get("run_id", "")), "evidence_file") not in artifact_keys:
            blockers.append(f"bundle handoff evidence artifact metadata missing: {item.get('run_id', '')}")
        if not isinstance(artifacts, dict) or not artifacts.get("manifest_file"):
            blockers.append(f"bundle handoff manifest_file missing: {item.get('run_id', '')}")
        elif (str(data.get("run_id", "")), "manifest_file") not in artifact_keys:
            blockers.append(f"bundle handoff manifest artifact metadata missing: {item.get('run_id', '')}")
        if not isinstance(provenance, dict) or "source_audit" not in provenance:
            blockers.append(f"bundle handoff source_audit missing: {item.get('run_id', '')}")
        resume = replay_handoff(path, workspace=target)
        replay_ok = resume.get("ok") is True
        if replay_ok:
            ready_records += 1
        if item.get("replay_ok") is not replay_ok:
            blockers.append(f"bundle handoff replay metadata mismatch: {item.get('run_id', '')}")
        if item.get("replay_blockers", []) != resume.get("blockers", []):
            blockers.append(f"bundle handoff replay blockers metadata mismatch: {item.get('run_id', '')}")
        if not replay_ok:
            blockers.append(f"bundle handoff replay not ready: {item.get('run_id', '')}: {resume.get('blockers', [])}")
    if handoffs.get("ready_records", 0) != ready_records:
        blockers.append("bundle handoff ready_records mismatch")
    return blockers


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _scan_bundle_for_secrets(target: Path) -> list[str]:
    try:
        from .governance import scan_secrets
    except Exception:
        return []
    blockers = []
    for path in target.rglob("*") if target.is_dir() else []:
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".json", ".jsonl"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for hit in scan_secrets(text):
            rel = path.relative_to(target).as_posix()
            blockers.append(f"possible secret in bundle file {rel}: {hit.get('pattern', '')}")
    return blockers


def _verify_ws_runtime_bundle(runtime_log_path: Path, chain: dict[str, Any] | None = None) -> list[str]:
    records = _load_jsonl(str(runtime_log_path))
    events = {str(item.get("event", "")) for item in records}
    blockers = []
    service_starts = [item for item in records if item.get("event") == "service_start"]
    if not service_starts:
        blockers.append("bundle ws runtime missing service_start")
    if service_starts:
        latest_start = service_starts[-1]
        required_start_fields = (
            "profile",
            "transport",
            "workspace",
            "default_model",
            "ack_deadline_seconds",
            "smoke_mode",
            "event_store_path",
            "job_store_path",
            "log_path",
            "smoke_evidence_path",
            "runtime_lock_path",
        )
        missing_start_fields = [
            field for field in required_start_fields if latest_start.get(field) in (None, "")
        ]
        if missing_start_fields:
            blockers.append(f"bundle ws runtime service_start missing fields: {missing_start_fields}")
        if latest_start.get("transport") != "ws":
            blockers.append("bundle ws runtime service_start transport is not ws")
        if latest_start.get("smoke_mode") is not False:
            blockers.append("bundle ws runtime service_start smoke_mode must be false")
    if "ws_transport_start" not in events:
        blockers.append("bundle ws runtime missing ws_transport_start")
    ws_events = [item for item in records if item.get("event") == "ws_event_received"]
    if not ws_events:
        blockers.append("bundle ws runtime missing ws_event_received")
    if any(item.get("ack_within_deadline") is False for item in ws_events):
        blockers.append("bundle ws runtime has ack deadline miss")
    if any(item.get("ack_latency_ms") in (None, "") or item.get("ack_deadline_ms") in (None, "") for item in ws_events):
        blockers.append("bundle ws runtime missing ack metrics")
    blockers.extend(_verify_ws_smoke_scenario_binding(records, chain or {}))
    return blockers


def _verify_ws_live_provenance_runtime_binding(runtime_log_path: Path, manifest: dict[str, Any]) -> list[str]:
    provenance = manifest.get("live_provenance", {}) if isinstance(manifest, dict) else {}
    expected = str(provenance.get("ws_sdk_session_id", "") if isinstance(provenance, dict) else "").strip()
    if not expected:
        return []
    records = _load_jsonl(str(runtime_log_path))
    service_starts = [item for item in records if item.get("event") == "service_start"]
    transport_starts = [item for item in records if item.get("event") == "ws_transport_start"]
    blockers: list[str] = []
    latest_service = service_starts[-1] if service_starts else {}
    latest_transport = transport_starts[-1] if transport_starts else {}
    service_value = str(latest_service.get("ws_sdk_session_id", "")).strip()
    transport_value = str(latest_transport.get("ws_sdk_session_id", "")).strip()
    missing = []
    if not service_value:
        missing.append("service_start")
    if not transport_value:
        missing.append("ws_transport_start")
    if missing:
        blockers.append(f"bundle ws runtime missing live provenance session marker: {', '.join(missing)}")
        return blockers
    mismatched = []
    if service_value != expected:
        mismatched.append("service_start")
    if transport_value != expected:
        mismatched.append("ws_transport_start")
    if mismatched:
        blockers.append(f"bundle ws runtime live provenance session mismatch: {', '.join(mismatched)}")
    return blockers


def _verify_ws_smoke_scenario_binding(records: list[dict[str, Any]], chain: dict[str, Any]) -> list[str]:
    smoke = chain.get("smoke", {}) if isinstance(chain, dict) else {}
    passed = set(smoke.get("passed", [])) if isinstance(smoke.get("passed", []), list) else set()
    correlation = chain.get("correlation", {}) if isinstance(chain, dict) else {}
    chains = correlation.get("chains", []) if isinstance(correlation.get("chains", []), list) else []
    by_scenario = {
        str(item.get("scenario", "")): item
        for item in chains
        if isinstance(item, dict)
    }
    required = sorted(set(REQUIRED_1_0_WS_SCENARIOS) & passed)
    blockers: list[str] = []
    for scenario in required:
        event_key = str(by_scenario.get(scenario, {}).get("event_key", ""))
        ws = _scenario_ws_ack_status(records, event_key=event_key)
        if not event_key:
            blockers.append(f"bundle ws scenario missing event_key: {scenario}")
            continue
        if not ws["seen"]:
            blockers.append(f"bundle ws scenario missing ws_event_received: {scenario}")
        elif ws["ack_within_deadline"] is not True:
            blockers.append(f"bundle ws scenario ack deadline miss: {scenario}")
        if ws["seen"] and (ws["ack_latency_ms"] in (None, "") or ws["ack_deadline_ms"] in (None, "")):
            blockers.append(f"bundle ws scenario missing ack metrics: {scenario}")
    return blockers


def _redact_sensitive_fields(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if _is_sensitive_field(str(key)):
                redacted[key] = "***"
            else:
                redacted[key] = _redact_sensitive_fields(item)
        return redacted
    if isinstance(value, list):
        return [_redact_sensitive_fields(item) for item in value]
    if isinstance(value, str):
        return redact_secrets(value)
    return value


def _is_sensitive_field(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in ("secret", "token", "api_key", "apikey", "authorization", "password"))


def _latest_job_records(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest = {}
    for item in records:
        job_id = item.get("id")
        if job_id:
            latest[str(job_id)] = item
    return latest


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _scenario_has_outbox_success(logs: list[dict[str, Any]], *, scenario: str, event_key: str) -> bool:
    if not event_key:
        return False
    if scenario == "card_fallback":
        return any(
            item.get("event") == "outbox_delivery"
            and item.get("success") is True
            and item.get("fallback") is True
            and item.get("correlation_id") == event_key
            for item in logs
        )
    return any(
        item.get("event") == "outbox_delivery"
        and item.get("success") is True
        and item.get("correlation_id") == event_key
        for item in logs
    )


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact_value(item) for key, item in value.items()}
    return value
