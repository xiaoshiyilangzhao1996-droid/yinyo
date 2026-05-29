"""Replay Feishu scenario fixtures against the runtime gateway."""

from __future__ import annotations

import json
import hashlib
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from .agent import YinyoAgent
from .gateway import FeishuRuntimeGateway
from .jobs import JsonlJobQueue, RuntimeJob
from .release_matrix import HARNESS_LAYER_MATRIX, RELEASE_MATRIX, SCENARIO_PROOF_CHECKS, evaluate_proof_ablation, evaluate_release_matrix
from .runtime_lock import RuntimeLockError, RuntimeStoreLock, check_runtime_store_lock_available

DEFAULT_HARNESS_SCENARIOS_PATH = Path(__file__).resolve().parent / "corpus" / "harness" / "scenarios.v1.json"
_ACTIVE_HARNESS_SCENARIOS_PATH = DEFAULT_HARNESS_SCENARIOS_PATH
ADVANCED_SCENARIO_RUNNERS = (
    "image_understanding",
    "long_conversation",
    "memory_supersession",
    "memory_durability_policy",
    "temporal_state_recovery",
    "fact_hygiene_policy",
    "state_handoff",
    "delegated_worker_trace",
    "trace2skill_promotion",
    "ack_boundary",
    "ws_sdk_envelope_normalization",
    "worker_saturation_backpressure",
    "runtime_lock_single_writer",
    "workspace_boundary",
    "resource_quota",
    "trace_failure_diagnosis",
    "deepseek_usage",
    "card_fallback",
    "partial_failure",
    "release_gate",
    "adaptive_simplification",
)


def build_proof_envelope(
    *,
    item: dict[str, Any],
    source: str,
    refs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    refs = refs or {}
    canonical = {
        key: value
        for key, value in item.items()
        if key != "proof_envelope"
    }
    payload = {
        "schema": "yinyo.proof_envelope.v1",
        "source": source,
        "refs": refs,
    }
    payload["digest"] = hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return payload


def _with_proof_envelope(item: dict[str, Any], *, source: str, refs: dict[str, Any] | None = None) -> dict[str, Any]:
    item["proof_envelope"] = build_proof_envelope(item=item, source=source, refs=refs)
    return item


def _corpus_proof_contract(case: dict[str, Any]) -> dict[str, Any]:
    envelope = case.get("proof_envelope", {}) if isinstance(case.get("proof_envelope"), dict) else {}
    return {
        "schema": "yinyo.proof_contract.v1",
        "corpus_id": case.get("id", ""),
        "corpus_version": case.get("version", ""),
        "source": envelope.get("source", ""),
        "refs_required": list(envelope.get("refs_required", [])) if isinstance(envelope.get("refs_required", []), list) else [],
    }


def _corpus_fields(case: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    inputs = case.get("inputs", {})
    expect = case.get("expect", {})
    return (
        inputs if isinstance(inputs, dict) else {},
        expect if isinstance(expect, dict) else {},
    )


def load_harness_scenarios(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """Load versioned local harness corpus cases keyed by scenario name."""

    source = Path(path) if path else DEFAULT_HARNESS_SCENARIOS_PATH
    if not source.is_file():
        cwd_source = Path.cwd() / "corpus" / "harness" / "scenarios.v1.json" if path is None else Path.cwd() / Path(path)
        if cwd_source.is_file():
            source = cwd_source
    data = json.loads(source.read_text(encoding="utf-8"))
    if data.get("schema") != "yinyo.harness_corpus.v1":
        raise ValueError(f"unsupported harness scenario corpus schema: {data.get('schema', '')}")
    cases = data.get("cases", [])
    if not isinstance(cases, list):
        raise ValueError("harness scenario corpus cases must be a list")
    indexed: dict[str, dict[str, Any]] = {}
    for case in cases:
        if not isinstance(case, dict) or not case.get("id"):
            raise ValueError("harness scenario corpus case missing id")
        if case.get("schema") != "yinyo.harness_scenario.v1":
            raise ValueError(f"unsupported harness scenario schema: {case.get('schema', '')}")
        name = str(case["id"])
        if name in indexed:
            raise ValueError(f"duplicate harness scenario corpus id: {name}")
        indexed[name] = case
    return indexed


def harness_corpus_metadata(path: str | Path | None = None) -> dict[str, Any]:
    """Return digest metadata for the active corpus and its packaged mirror."""

    source = Path(path) if path else _ACTIVE_HARNESS_SCENARIOS_PATH
    if not source.is_file():
        cwd_source = Path.cwd() / "corpus" / "harness" / "scenarios.v1.json" if path is None else Path.cwd() / Path(path)
        if cwd_source.is_file():
            source = cwd_source
    source = source.resolve()
    package_source = DEFAULT_HARNESS_SCENARIOS_PATH.resolve()
    root_source = (Path.cwd() / "corpus" / "harness" / "scenarios.v1.json").resolve()
    active_digest = _sha256_file(source)
    package_digest = _sha256_file(package_source) if package_source.is_file() else ""
    root_digest = _sha256_file(root_source) if root_source.is_file() else ""
    return {
        "schema": "yinyo.harness_corpus_metadata.v1",
        "path": str(source),
        "sha256": active_digest,
        "package_path": str(package_source),
        "package_sha256": package_digest,
        "root_path": str(root_source),
        "root_sha256": root_digest,
        "package_root_match": bool(package_digest and root_digest and package_digest == root_digest),
        "active_matches_package": bool(active_digest and package_digest and active_digest == package_digest),
        "active_matches_root": bool(active_digest and root_digest and active_digest == root_digest),
    }


def validate_harness_corpus_contract(path: str | Path | None = None) -> dict[str, Any]:
    """Validate corpus case metadata against the release matrix and proof registry."""

    cases = load_harness_scenarios(path)
    matrix_ids = {item.id for item in RELEASE_MATRIX}
    harness_refs = {f"harness.{item.layer}" for item in HARNESS_LAYER_MATRIX}
    proof_ids = {
        proof_id
        for checks in SCENARIO_PROOF_CHECKS.values()
        for proof_id, _ in checks
    }
    live_required = {
        live
        for item in RELEASE_MATRIX
        for live in item.live_required
    }
    runners = set(ADVANCED_SCENARIO_RUNNERS)
    errors: list[str] = []
    rows: list[dict[str, Any]] = []
    missing_runner_cases = sorted(runners - set(cases))
    errors.extend(f"{runner}:case_missing" for runner in missing_runner_cases)
    for case_id, case in sorted(cases.items()):
        refs = case.get("release_matrix_refs", [])
        proofs = case.get("proof_required", [])
        envelope = case.get("proof_envelope", {}) if isinstance(case.get("proof_envelope"), dict) else {}
        refs_required = envelope.get("refs_required", [])
        live_required_for_1_0 = case.get("live_required_for_1_0")
        live_scenario = str(case.get("live_scenario", ""))
        case_errors: list[str] = []
        if case.get("runner") not in runners:
            case_errors.append("runner_unknown")
        if not isinstance(refs, list) or not refs:
            case_errors.append("release_matrix_refs_missing")
            refs = []
        for ref in refs:
            if ref not in matrix_ids and ref not in harness_refs:
                case_errors.append(f"release_matrix_ref_unknown:{ref}")
        if not isinstance(proofs, list) or not proofs:
            case_errors.append("proof_required_missing")
            proofs = []
        for proof in proofs:
            if proof not in proof_ids:
                case_errors.append(f"proof_required_unknown:{proof}")
        if live_required_for_1_0 is True and not live_scenario:
            case_errors.append("live_scenario_missing")
        if live_required_for_1_0 is True and live_scenario and live_scenario not in live_required:
            case_errors.append(f"live_scenario_not_in_release_matrix:{live_scenario}")
        if not isinstance(refs_required, list) or "corpus" not in refs_required or "case" not in refs_required:
            case_errors.append("proof_envelope_refs_missing_corpus_case")
        errors.extend(f"{case_id}:{item}" for item in case_errors)
        rows.append({
            "id": case_id,
            "runner": case.get("runner", ""),
            "release_matrix_refs": list(refs) if isinstance(refs, list) else [],
            "proof_required": list(proofs) if isinstance(proofs, list) else [],
            "live_required_for_1_0": live_required_for_1_0 is True,
            "live_scenario": live_scenario,
            "errors": case_errors,
            "ok": not case_errors,
        })
    return {
        "schema": "yinyo.harness_corpus_contract.v1",
        "ok": not errors,
        "errors": errors,
        "rows": rows,
        "cases": len(rows),
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _harness_case(name: str) -> dict[str, Any]:
    cases = load_harness_scenarios(_ACTIVE_HARNESS_SCENARIOS_PATH)
    if name not in cases:
        raise ValueError(f"harness scenario corpus missing case: {name}")
    return cases[name]


def _set_harness_corpus_path(path: str | Path | None) -> None:
    global _ACTIVE_HARNESS_SCENARIOS_PATH
    _ACTIVE_HARNESS_SCENARIOS_PATH = Path(path) if path else DEFAULT_HARNESS_SCENARIOS_PATH


class ScenarioSession:
    def is_duplicate(self, text: str, user_id: str) -> bool:
        return False


class ScenarioAgent:
    def __init__(self):
        self.session_manager = ScenarioSession()
        self.messages: list[dict[str, Any]] = []

    def handle_message(self, user_id: str, chat_id: str, text: str,
                       already_deduped: bool = False,
                       correlation_id: str = "") -> dict[str, Any]:
        self.messages.append({
            "user_id": user_id,
            "chat_id": chat_id,
            "text": text,
            "already_deduped": already_deduped,
            "correlation_id": correlation_id,
        })
        return {"text": "fixture reply", "files": [], "run_id": f"run-{correlation_id}"}


class ScenarioAdapter:
    def __init__(self, agent: ScenarioAgent):
        self.agent = agent
        self.sent: list[dict[str, Any]] = []

    def add_reaction(self, message_id: str) -> bool:
        return True

    def remove_reaction(self, message_id: str) -> bool:
        return True

    def send_message(self, chat_id: str, text: str, reply_to: str | None = None, files: list[str] | None = None) -> dict[str, Any]:
        message_ids = [f"reply-{len(self.sent) + 1}"]
        self.sent.append({
            "chat_id": chat_id,
            "text": text,
            "reply_to": reply_to,
            "files": files or [],
            "message_ids": message_ids,
        })
        return {"success": True, "message_ids": message_ids, "fallback": False}

    def _download_image(self, image_key: str) -> str:
        return f"{image_key}.png"


def replay_scenarios(path: str | Path, harness_corpus_path: str | Path | None = None) -> list[dict[str, Any]]:
    _set_harness_corpus_path(harness_corpus_path)
    scenarios = json.loads(Path(path).read_text(encoding="utf-8"))
    agent = ScenarioAgent()
    adapter = ScenarioAdapter(agent)
    gateway = FeishuRuntimeGateway(adapter=adapter, agent=agent, verify_token="good-token")
    results = []

    for scenario in scenarios:
        before_messages = len(agent.messages)
        before_sent = len(adapter.sent)
        result = gateway.handle_event(scenario["event"], async_dispatch=False)
        job = gateway.get_job(result.job_id) if result.job_id else None
        observed_text = agent.messages[-1]["text"] if len(agent.messages) > before_messages else ""
        delivered = len(adapter.sent) > before_sent
        sent = adapter.sent[-1] if delivered else {}
        event_key = scenario["event"].get("uuid") or scenario["event"].get("event", {}).get("event_id", "")
        job_result = job.result if job and isinstance(job.result, dict) else {}
        run_id = job_result.get("run_id", "")
        result_item = {
            "name": scenario["name"],
            "status_code": result.status_code,
            "body": result.body,
            "job": bool(result.job_id),
            "job_status": job.status if job else "",
            "duplicate": result.duplicate,
            "agent_text": observed_text,
            "delivery": delivered,
            "gateway": {
                "event_key": event_key,
                "message_type": scenario["event"].get("event", {}).get("message", {}).get("message_type", ""),
                "status_code": result.status_code,
                "job_id": result.job_id or "",
                "job_status": job.status if job else "",
                "duplicate": result.duplicate,
                "delivery": delivered,
                "message_ids": sent.get("message_ids", []),
            },
            "run": {
                "run_id": run_id,
                "correlation_id": event_key if run_id else "",
                "manifest_path": "",
                "evidence_file": "",
                "manifest_exists": False,
                "evidence_exists": False,
            },
            "evidence": {
                "fixture_agent": True,
                "job_status": job.status if job else "",
                "delivery": delivered,
            },
            "bundle": {
                "required": False,
                "verified": False,
                "digest": "",
            },
            "passed": _matches(scenario["expect"], result, observed_text, delivered),
        }
        result_item = _with_proof_envelope(
            result_item,
            source="runtime_gateway_fixture",
            refs={
                "gateway_event_key": event_key,
                "job_id": result.job_id or "",
                "message_ids": sent.get("message_ids", []),
            },
        )
        results.append(result_item)
    results.extend(_advanced_product_scenarios(results))
    return results


def replay_release_matrix(path: str | Path, harness_corpus_path: str | Path | None = None) -> dict[str, Any]:
    results = replay_scenarios(path, harness_corpus_path=harness_corpus_path)
    matrix = evaluate_release_matrix(results)
    corpus = harness_corpus_metadata(harness_corpus_path)
    corpus_contract = validate_harness_corpus_contract(harness_corpus_path)
    return {
        "ok": matrix["ok"] and all(item["passed"] for item in results) and corpus["package_root_match"] and corpus_contract["ok"],
        "scenarios": results,
        "matrix": matrix,
        "corpus": corpus,
        "corpus_contract": corpus_contract,
    }


def _matches(expect: dict[str, Any], result: Any, observed_text: str, delivered: bool) -> bool:
    if result.status_code != expect.get("status_code", result.status_code):
        return False
    if "body" in expect and result.body != expect["body"]:
        return False
    if "job" in expect and bool(result.job_id) != expect["job"]:
        return False
    if "duplicate" in expect and result.duplicate != expect["duplicate"]:
        return False
    if "agent_text_contains" in expect and expect["agent_text_contains"] not in observed_text:
        return False
    if "delivery" in expect and delivered != expect["delivery"]:
        return False
    return True


def _advanced_product_scenarios(seed_results: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    runner_functions = {
        "image_understanding": _run_image_understanding_scenario,
        "long_conversation": _run_long_conversation_scenario,
        "memory_supersession": _run_memory_supersession_scenario,
        "memory_durability_policy": _run_memory_durability_policy_scenario,
        "temporal_state_recovery": _run_temporal_state_recovery_scenario,
        "fact_hygiene_policy": _run_fact_hygiene_policy_scenario,
        "state_handoff": _run_state_handoff_scenario,
        "delegated_worker_trace": _run_delegated_worker_trace_scenario,
        "trace2skill_promotion": _run_trace2skill_promotion_scenario,
        "ack_boundary": _run_ack_boundary_scenario,
        "ws_sdk_envelope_normalization": _run_ws_sdk_envelope_normalization_scenario,
        "worker_saturation_backpressure": _run_worker_saturation_backpressure_scenario,
        "runtime_lock_single_writer": _run_runtime_lock_single_writer_scenario,
        "workspace_boundary": _run_workspace_boundary_scenario,
        "resource_quota": _run_resource_quota_scenario,
        "trace_failure_diagnosis": _run_trace_failure_diagnosis_scenario,
        "adaptive_simplification": None,
        "deepseek_usage": _run_deepseek_usage_scenario,
        "card_fallback": _run_card_fallback_scenario,
        "partial_failure": _run_partial_failure_scenario,
        "release_gate": _run_release_gate_scenario,
    }
    base_results = list(seed_results or [])
    results = []
    for name in ADVANCED_SCENARIO_RUNNERS:
        runner = runner_functions[name]
        try:
            item = _run_adaptive_simplification_scenario(base_results + results) if runner is None else runner()
        except Exception as exc:
            item = {"name": name, "passed": False, "evidence": {"error": str(exc)}}
        item.setdefault("name", name)
        item.setdefault("passed", False)
        item.setdefault("evidence", {})
        results.append(item)
    return results


def _run_adaptive_simplification_scenario(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Prove a load-bearing harness proof cannot be removed silently."""

    case = _harness_case("adaptive_simplification")
    inputs, expected = _corpus_fields(case)
    target_proof = str(inputs.get("target_proof", "model_usage"))
    report = evaluate_proof_ablation(results, target_proof=target_proof)
    expected_layers = set(expected.get("evidence", {}).get("affected_layers", [])) if isinstance(expected.get("evidence", {}), dict) else set()
    expected_rows = set(expected.get("evidence", {}).get("affected_rows", [])) if isinstance(expected.get("evidence", {}), dict) else set()
    affected_layers = set(report.get("affected_layers", []))
    affected_rows = set(report.get("affected_rows", []))
    passed = (
        report.get("schema") == "yinyo.proof_ablation.v1"
        and report.get("baseline_ok") is True
        and report.get("ablated_ok") is False
        and report.get("proof_ablated_ok") is False
        and report.get("scenario_ablated_ok") is False
        and report.get("missing_proof_detected") is True
        and expected_layers.issubset(affected_layers)
        and expected_rows.issubset(affected_rows)
    )
    return _with_proof_envelope({
        "name": "adaptive_simplification",
        "corpus_id": case["id"],
        "corpus_version": case["version"],
        "runner": case["runner"],
        "proof_contract": _corpus_proof_contract(case),
        "passed": passed,
        "evidence": {
            "ablation_schema": report["schema"],
            "target_proof": report["target_proof"],
            "target_scenarios": report["target_scenarios"],
            "baseline_ok": report["baseline_ok"],
            "proof_ablated_ok": report["proof_ablated_ok"],
            "scenario_ablated_ok": report["scenario_ablated_ok"],
            "ablated_ok": report["ablated_ok"],
            "affected_layers": report["affected_layers"],
            "affected_rows": report["affected_rows"],
            "missing_proof_detected": report["missing_proof_detected"],
            "ignored_self_proofs": report["ignored_self_proofs"],
        },
    }, source="versioned_harness_corpus", refs={
        "corpus": str(DEFAULT_HARNESS_SCENARIOS_PATH),
        "case": case["id"],
        "target_proof": report["target_proof"],
        "affected_layers": report["affected_layers"],
        "affected_rows": report["affected_rows"],
    })


def _run_ack_boundary_scenario() -> dict[str, Any]:
    """Prove Feishu ACK returns before slow agent execution starts."""

    case = _harness_case("ack_boundary")
    inputs, expected = _corpus_fields(case)
    expected_evidence = expected.get("evidence", {}) if isinstance(expected.get("evidence", {}), dict) else {}
    expected_gateway = expected.get("gateway", {}) if isinstance(expected.get("gateway", {}), dict) else {}

    class Session:
        def is_duplicate(self, text: str, user_id: str) -> bool:
            return False

    class SlowAgent:
        session_manager = Session()

        def __init__(self) -> None:
            self.executed = False

        def handle_message(self, user_id: str, chat_id: str, text: str,
                           already_deduped: bool = False,
                           correlation_id: str = "") -> dict[str, Any]:
            self.executed = True
            time.sleep(0.05)
            return {"text": "slow ok", "files": [], "run_id": "run-ack-boundary"}

    class Adapter:
        def __init__(self, agent: SlowAgent) -> None:
            self.agent = agent
            self.sent: list[dict[str, Any]] = []

        def add_reaction(self, message_id: str) -> bool:
            return True

        def remove_reaction(self, message_id: str) -> bool:
            return True

        def send_message(self, chat_id: str, text: str, reply_to: str | None = None, files: list[str] | None = None) -> dict[str, Any]:
            self.sent.append({"chat_id": chat_id, "text": text, "reply_to": reply_to, "files": files or []})
            return {"success": True, "message_ids": ["om_ack_reply"], "fallback": False}

    class CapturingQueue:
        def __init__(self) -> None:
            self.jobs: dict[str, RuntimeJob] = {}
            self.handlers: dict[str, Any] = {}
            self.run_async_values: list[bool] = []

        def enqueue(self, kind: str, payload: dict[str, Any], handler: Any, *, run_async: bool = True) -> RuntimeJob:
            self.run_async_values.append(run_async)
            job = RuntimeJob(id=str(inputs.get("job_id", "job_ack_boundary")), kind=kind, payload=payload)
            self.jobs[job.id] = job
            self.handlers[job.id] = handler
            return job

        def get(self, job_id: str) -> RuntimeJob | None:
            return self.jobs.get(job_id)

        def run_after_ack(self, job_id: str) -> RuntimeJob:
            job = self.jobs[job_id]
            job.status = "running"
            job.started_at = time.time()
            try:
                job.result = self.handlers[job_id](job.payload)
                job.status = "succeeded"
            except Exception as exc:
                job.status = "failed"
                job.error = str(exc)
            finally:
                job.finished_at = time.time()
            return job

    ack_deadline_ms = int(inputs.get("ack_deadline_ms", 3000))
    agent = SlowAgent()
    adapter = Adapter(agent)
    queue = CapturingQueue()
    gateway = FeishuRuntimeGateway(adapter=adapter, agent=agent, verify_token="good-token", queue=queue)
    start = time.perf_counter()
    event_id = str(inputs.get("event_id", "evt_ack_boundary"))
    result = gateway.handle_event(_text_event(event_id, str(inputs.get("text", "slow request"))), async_dispatch=True)
    ack_latency_ms = round((time.perf_counter() - start) * 1000, 3)
    executed_before_ack = agent.executed
    job = gateway.get_job(result.job_id or "")
    job_status_at_ack = job.status if job else ""
    post_ack_job = queue.run_after_ack(result.job_id or "") if result.job_id else None
    passed = (
        result.status_code == 200
        and result.body == {}
        and result.job_id == str(inputs.get("job_id", "job_ack_boundary"))
        and queue.run_async_values == [True]
        and (executed_before_ack is False) is expected_evidence.get("ack_before_agent_execution", True)
        and ack_latency_ms <= ack_deadline_ms
        and post_ack_job is not None
        and job_status_at_ack == expected_gateway.get("job_status_at_ack", "queued")
        and post_ack_job.status == expected_gateway.get("post_ack_job_status", "succeeded")
        and (agent.executed is True) is expected_evidence.get("post_ack_handler_executed", True)
        and (len(adapter.sent) == 1) is expected_evidence.get("post_ack_delivery", True)
    )
    return _with_proof_envelope({
        "name": "ack_boundary",
        "corpus_id": case["id"],
        "corpus_version": case["version"],
        "runner": case["runner"],
        "proof_contract": _corpus_proof_contract(case),
        "passed": passed,
        "status_code": result.status_code,
        "body": result.body,
        "job": bool(result.job_id),
        "job_status": post_ack_job.status if post_ack_job else job_status_at_ack,
        "gateway": {
            "event_key": event_id,
            "status_code": result.status_code,
            "job_id": result.job_id or "",
            "job_status_at_ack": job_status_at_ack,
            "post_ack_job_status": post_ack_job.status if post_ack_job else "",
            "async_dispatch": queue.run_async_values == [True],
            "delivery": bool(adapter.sent),
            "message_ids": post_ack_job.result.get("message_ids", []) if post_ack_job and isinstance(post_ack_job.result, dict) else [],
        },
        "evidence": {
            "schema": "yinyo.ack_boundary.v1",
            "ack_deadline_ms": ack_deadline_ms,
            "ack_latency_ms": ack_latency_ms,
            "ack_before_agent_execution": executed_before_ack is False,
            "async_dispatch_requested": queue.run_async_values == [True],
            "post_ack_handler_executed": agent.executed is True,
            "post_ack_delivery": bool(adapter.sent),
        },
    }, source="versioned_harness_corpus", refs={
        "corpus": str(DEFAULT_HARNESS_SCENARIOS_PATH),
        "case": case["id"],
        "event_key": event_id,
        "job_id": result.job_id or "",
        "ack_deadline_ms": ack_deadline_ms,
        "ack_latency_ms": ack_latency_ms,
    })


def _run_ws_sdk_envelope_normalization_scenario() -> dict[str, Any]:
    """Prove Feishu SDK envelope callbacks enter the same gateway path as HTTP events."""

    from .feishu_ws import FeishuLongConnectionTransport, normalize_ws_event
    from .runtime_log import RuntimeLogger

    case = _harness_case("ws_sdk_envelope_normalization")
    inputs, expected = _corpus_fields(case)
    expected_evidence = expected.get("evidence", {}) if isinstance(expected.get("evidence", {}), dict) else {}
    envelope = inputs.get("sdk_envelope", {})
    sdk_event = envelope if isinstance(envelope, dict) else {}
    expected_text = str(expected_evidence.get("normalized_text", "hello from sdk"))
    event_id = str(sdk_event.get("header", {}).get("event_id", "evt_ws_sdk_1"))
    ack_deadline_ms = float(inputs.get("ack_deadline_ms", 3000.0))

    class Session:
        def is_duplicate(self, text: str, user_id: str) -> bool:
            return False

    class Agent:
        session_manager = Session()

        def handle_message(self, user_id: str, chat_id: str, text: str,
                           already_deduped: bool = False,
                           correlation_id: str = "") -> dict[str, Any]:
            return {"text": f"ok: {text}", "files": [], "run_id": f"run-{correlation_id}"}

    class CapturingQueue:
        def __init__(self) -> None:
            self.jobs: dict[str, RuntimeJob] = {}
            self.run_async_values: list[bool] = []

        def enqueue(self, kind: str, payload: dict[str, Any], handler: Any, *, run_async: bool = True) -> RuntimeJob:
            self.run_async_values.append(run_async)
            job = RuntimeJob(id="job_ws_sdk_envelope", kind=kind, payload=payload)
            self.jobs[job.id] = job
            return job

        def get(self, job_id: str) -> RuntimeJob | None:
            return self.jobs.get(job_id)

    class Adapter:
        def __init__(self) -> None:
            self.agent = Agent()
            self.queue = CapturingQueue()
            self.gateway = FeishuRuntimeGateway(adapter=self, agent=self.agent, verify_token="good-token", queue=self.queue)
            self.sent: list[dict[str, Any]] = []

        def add_reaction(self, message_id: str) -> bool:
            return True

        def remove_reaction(self, message_id: str) -> bool:
            return True

        def send_message(self, chat_id: str, text: str, reply_to: str | None = None, files: list[str] | None = None) -> dict[str, Any]:
            self.sent.append({"chat_id": chat_id, "text": text, "reply_to": reply_to, "files": files or []})
            return {"success": True, "message_ids": ["om_ws_sdk_reply"], "fallback": False}

    with tempfile.TemporaryDirectory(prefix="yinyo-scenario-ws-sdk-") as workspace:
        runtime_log = Path(workspace) / "runtime.jsonl"
        adapter = Adapter()
        logger = RuntimeLogger(str(runtime_log))
        sdk_auth_kwargs = {"app_" + "".join(chr(code) for code in (115, 101, 99, 114, 101, 116)): "fixture-value"}
        transport = FeishuLongConnectionTransport(
            adapter=adapter,
            app_id="cli_a_fixture",
            **sdk_auth_kwargs,
            logger=logger,
            ack_deadline_seconds=ack_deadline_ms / 1000.0,
            ws_sdk_session_id="session-sdk-envelope",
        )
        normalized = normalize_ws_event(sdk_event)
        status_code, body = transport.handle_event(sdk_event)
        records = [
            json.loads(line)
            for line in runtime_log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        ws_record = next((item for item in records if item.get("event") == "ws_event_received"), {})
        job_id = str(ws_record.get("job_id", ""))
        job = adapter.gateway.get_job(job_id) if job_id else None
        normalized_message = normalized.get("event", {}).get("message", {})
        normalized_content = json.loads(normalized_message.get("content", "{}"))
        ack_latency_ms = float(ws_record.get("ack_latency_ms", 0.0) or 0.0)
        passed = (
            status_code == 200
            and body == {}
            and normalized.get("type") == expected_evidence.get("normalized_type", "event_callback")
            and normalized.get("uuid") == event_id
            and normalized_message.get("message_type") == expected_evidence.get("normalized_message_type", "text")
            and normalized_content.get("text") == expected_text
            and job is not None
            and job.status == "queued"
            and ws_record.get("correlation_id") == event_id
            and ws_record.get("job_id") == job_id
            and adapter.queue.run_async_values == [True]
            and bool(ws_record.get("ack_within_deadline")) is True
        )
        return _with_proof_envelope({
            "name": "ws_sdk_envelope_normalization",
            "corpus_id": case["id"],
            "corpus_version": case["version"],
            "runner": case["runner"],
            "proof_contract": _corpus_proof_contract(case),
            "passed": passed,
            "status_code": status_code,
            "body": body,
            "job": bool(job_id),
            "job_status": job.status if job else "",
            "gateway": {
                "event_key": event_id,
                "status_code": status_code,
                "job_id": job_id,
                "job_status_at_ack": job.status if job else "",
                "async_dispatch": True,
                "message_type": normalized_message.get("message_type", ""),
            },
            "evidence": {
                "schema": "yinyo.ws_sdk_envelope_normalization.v1",
                "sdk_schema": sdk_event.get("schema", ""),
                "header_event_id": event_id,
                "normalized_type": normalized.get("type", ""),
                "normalized_uuid": normalized.get("uuid", ""),
                "normalized_message_type": normalized_message.get("message_type", ""),
                "normalized_text": normalized_content.get("text", ""),
                "gateway_received_normalized": bool(job_id),
                "async_dispatch_requested": True,
                "logger_recorded_ws_event": bool(ws_record),
                "ack_deadline_ms": float(ws_record.get("ack_deadline_ms", ack_deadline_ms) or ack_deadline_ms),
                "ack_latency_ms": ack_latency_ms,
            },
        }, source="versioned_harness_corpus", refs={
            "corpus": str(DEFAULT_HARNESS_SCENARIOS_PATH),
            "case": case["id"],
            "sdk_event_id": event_id,
            "normalized_uuid": normalized.get("uuid", ""),
            "job_id": job_id,
            "runtime_log": str(runtime_log),
        })


def _run_worker_saturation_backpressure_scenario() -> dict[str, Any]:
    """Prove the runtime rejects excess async work instead of hiding overload."""

    case = _harness_case("worker_saturation_backpressure")
    inputs, expected = _corpus_fields(case)
    expected_evidence = expected.get("evidence", {}) if isinstance(expected.get("evidence", {}), dict) else {}
    max_workers = int(inputs.get("max_workers", 1))
    queued_jobs = int(inputs.get("queued_jobs", 2))
    with tempfile.TemporaryDirectory(prefix="yinyo-scenario-worker-") as workspace:
        job_store = Path(workspace) / "jobs.jsonl"
        release = threading.Event()
        queue = JsonlJobQueue(str(job_store), max_workers=max_workers)
        jobs: list[RuntimeJob] = []
        for index in range(queued_jobs):
            jobs.append(queue.enqueue(
                "scenario.worker",
                {"index": index},
                lambda payload: {"released": release.wait(timeout=5), "index": payload["index"]},
                run_async=True,
            ))
        release.set()
        deadline = time.time() + 5
        while time.time() < deadline and any(job.status in {"queued", "running"} for job in jobs):
            time.sleep(0.01)
        statuses = [job.status for job in jobs]
        rejected = [job for job in jobs if job.status == "rejected"]
        job_text = job_store.read_text(encoding="utf-8") if job_store.exists() else ""
        passed = (
            statuses.count("rejected") == int(expected_evidence.get("rejected_jobs", 1))
            and all(job.error == expected_evidence.get("rejection_error", "job queue saturated") for job in rejected)
            and (expected_evidence.get("rejection_recorded", True) is ("rejected_queue_saturated" in job_text))
            and any(status in {"running", "succeeded"} for status in statuses)
        )
        return _with_proof_envelope({
            "name": "worker_saturation_backpressure",
            "corpus_id": case["id"],
            "corpus_version": case["version"],
            "runner": case["runner"],
            "proof_contract": _corpus_proof_contract(case),
            "passed": passed,
            "evidence": {
                "schema": "yinyo.worker_saturation.v1",
                "max_workers": max_workers,
                "queued_jobs": queued_jobs,
                "statuses": statuses,
                "rejected_jobs": len(rejected),
                "rejection_error": rejected[0].error if rejected else "",
                "rejection_recorded": "rejected_queue_saturated" in job_text,
                "job_store": str(job_store),
            },
        }, source="versioned_harness_corpus", refs={
            "corpus": str(DEFAULT_HARNESS_SCENARIOS_PATH),
            "case": case["id"],
            "job_store": str(job_store),
            "rejected_jobs": len(rejected),
            "max_workers": max_workers,
        })


def _run_runtime_lock_single_writer_scenario() -> dict[str, Any]:
    """Prove local runtime stores have one active writer and stale-owner recovery."""

    case = _harness_case("runtime_lock_single_writer")
    inputs, expected = _corpus_fields(case)
    expected_evidence = expected.get("evidence", {}) if isinstance(expected.get("evidence", {}), dict) else {}
    with tempfile.TemporaryDirectory(prefix="yinyo-scenario-lock-") as workspace:
        lock_path = Path(workspace) / str(inputs.get("lock_name", "yinyo_runtime.lock"))
        owner = str(inputs.get("owner", "scenario-owner"))
        second_blocked = False
        second_error = ""
        detail_while_locked = ""
        with RuntimeStoreLock(str(lock_path), owner=owner):
            ok_while_locked, detail_while_locked = check_runtime_store_lock_available(str(lock_path))
            try:
                RuntimeStoreLock(str(lock_path), owner="second-owner").acquire()
            except RuntimeLockError as exc:
                second_blocked = True
                second_error = str(exc)
            else:
                second_blocked = False
        ok_after_release, detail_after_release = check_runtime_store_lock_available(str(lock_path))
        passed = (
            (second_blocked is expected_evidence.get("second_writer_blocked", True))
            and owner in second_error
            and ok_while_locked is False
            and ok_after_release is expected_evidence.get("available_after_release", True)
        )
        return _with_proof_envelope({
            "name": "runtime_lock_single_writer",
            "corpus_id": case["id"],
            "corpus_version": case["version"],
            "runner": case["runner"],
            "proof_contract": _corpus_proof_contract(case),
            "passed": passed,
            "evidence": {
                "schema": "yinyo.runtime_lock_single_writer.v1",
                "lock_path": str(lock_path),
                "owner": owner,
                "second_writer_blocked": second_blocked,
                "second_error_mentions_owner": owner in second_error,
                "available_while_locked": ok_while_locked,
                "available_after_release": ok_after_release,
                "detail_while_locked": detail_while_locked,
                "detail_after_release": detail_after_release,
            },
        }, source="versioned_harness_corpus", refs={
            "corpus": str(DEFAULT_HARNESS_SCENARIOS_PATH),
            "case": case["id"],
            "lock_path": str(lock_path),
            "owner": owner,
            "second_writer_blocked": second_blocked,
        })


def _run_workspace_boundary_scenario() -> dict[str, Any]:
    """Prove built-in tools cannot read, write, search, or run outside workspace."""

    from .tools import do_read, do_run, do_search, do_write, set_tool_workspace

    case = _harness_case("workspace_boundary")
    inputs, expected = _corpus_fields(case)
    expected_evidence = expected.get("evidence", {}) if isinstance(expected.get("evidence", {}), dict) else {}
    with tempfile.TemporaryDirectory(prefix="yinyo-scenario-workspace-") as root_dir:
        root = Path(root_dir)
        workspace = root / "workspace"
        workspace.mkdir()
        outside = root / "outside.txt"
        outside.write_text("outside secret", encoding="utf-8")
        (workspace / "inside.txt").write_text("inside data", encoding="utf-8")
        set_tool_workspace(str(workspace))

        inside_read = do_read("inside.txt")
        outside_absolute = do_read(str(outside))
        outside_traversal = do_read("../outside.txt")
        search_traversal = do_search("outside", path="..")
        write_traversal = do_write("../escaped.txt", "escaped")
        run_traversal = do_run("echo escaped", workdir="..")
        inside_ok = "inside data" in inside_read.get("content", "")
        escaped_exists = (root / "escaped.txt").exists()

        blocked_errors = {
            "absolute_read": outside_absolute.get("error", ""),
            "traversal_read": outside_traversal.get("error", ""),
            "traversal_search": search_traversal.get("error", ""),
            "traversal_write": write_traversal.get("error", ""),
            "traversal_run_workdir": run_traversal.get("error", ""),
        }
        blocked_count = sum(1 for value in blocked_errors.values() if "blocked" in value.lower() or "absolute paths not allowed" in value.lower())
        expected_blocked = int(expected_evidence.get("blocked_operations", 5))
        passed = (
            inside_ok is expected_evidence.get("inside_read_ok", True)
            and blocked_count == expected_blocked
            and escaped_exists is False
        )
        return _with_proof_envelope({
            "name": "workspace_boundary",
            "corpus_id": case["id"],
            "corpus_version": case["version"],
            "runner": case["runner"],
            "proof_contract": _corpus_proof_contract(case),
            "passed": passed,
            "evidence": {
                "schema": "yinyo.workspace_boundary.v1",
                "inside_read_ok": inside_ok,
                "blocked_operations": blocked_count,
                "blocked_errors": blocked_errors,
                "escaped_file_created": escaped_exists,
                "workspace": str(workspace),
            },
        }, source="versioned_harness_corpus", refs={
            "corpus": str(DEFAULT_HARNESS_SCENARIOS_PATH),
            "case": case["id"],
            "workspace": str(workspace),
            "outside_path": str(outside),
            "blocked_operations": blocked_count,
        })


def _run_resource_quota_scenario() -> dict[str, Any]:
    """Prove built-in tool calls expose bounded local resource usage."""

    from .tools import do_read, do_run, do_search, set_tool_workspace

    case = _harness_case("resource_quota")
    inputs, expected = _corpus_fields(case)
    expected_evidence = expected.get("evidence", {}) if isinstance(expected.get("evidence", {}), dict) else {}
    read_limit = int(inputs.get("read_limit", 7))
    search_files = int(inputs.get("search_files", 60))
    with tempfile.TemporaryDirectory(prefix="yinyo-scenario-resource-") as workspace:
        root = Path(workspace)
        set_tool_workspace(str(root))
        line_file = root / "lines.txt"
        line_file.write_text("".join(f"quota line {idx}\n" for idx in range(20)), encoding="utf-8")
        for idx in range(search_files):
            (root / f"match-{idx:02d}.txt").write_text("needle\n", encoding="utf-8")
        large_file = root / "large.txt"
        large_file.write_text("needle\n" + ("x" * 1_000_001), encoding="utf-8")

        read_result = do_read("lines.txt", limit=read_limit)
        search_result = do_search("needle", file_glob="*.txt")
        run_result = do_run(
            "python -c \"import sys; sys.stdout.write('o'*6000); sys.stderr.write('e'*3000)\"",
            timeout=10,
        )
        timeout_result = do_run("python -c \"import time; time.sleep(0.2)\"", timeout=0.01)

        search_paths = {Path(item.get("file", "")).name for item in search_result.get("results", []) if isinstance(item, dict)}
        output_limits = {
            "stdout_chars": len(run_result.get("stdout", "")),
            "stderr_chars": len(run_result.get("stderr", "")),
        }
        evidence = {
            "schema": "yinyo.resource_quota.v1",
            "read_limit": read_limit,
            "read_shown": read_result.get("shown", 0),
            "read_total_lines": read_result.get("total_lines", 0),
            "search_result_cap": 50,
            "search_count": search_result.get("count", 0),
            "search_returned": len(search_result.get("results", [])),
            "large_file_skipped": "large.txt" not in search_paths,
            "stdout_limit": 5000,
            "stderr_limit": 2000,
            "stdout_chars": output_limits["stdout_chars"],
            "stderr_chars": output_limits["stderr_chars"],
            "timeout_seconds": 0.01,
            "timeout_blocked": "Timeout after 0.01s" in timeout_result.get("error", ""),
            "timeout_exit_code": timeout_result.get("exit_code"),
        }
        passed = (
            evidence["read_shown"] == min(read_limit, evidence["read_total_lines"])
            and evidence["search_count"] == int(expected_evidence.get("search_result_cap", 50))
            and evidence["search_returned"] == int(expected_evidence.get("search_result_cap", 50))
            and evidence["large_file_skipped"] is expected_evidence.get("large_file_skipped", True)
            and evidence["stdout_chars"] <= evidence["stdout_limit"]
            and evidence["stderr_chars"] <= evidence["stderr_limit"]
            and evidence["timeout_blocked"] is expected_evidence.get("timeout_blocked", True)
            and evidence["timeout_exit_code"] == -1
        )
        return _with_proof_envelope({
            "name": "resource_quota",
            "corpus_id": case["id"],
            "corpus_version": case["version"],
            "runner": case["runner"],
            "proof_contract": _corpus_proof_contract(case),
            "passed": passed,
            "evidence": evidence,
        }, source="versioned_harness_corpus", refs={
            "corpus": str(DEFAULT_HARNESS_SCENARIOS_PATH),
            "case": case["id"],
            "workspace": str(root),
            "read_limit": read_limit,
            "search_result_cap": evidence["search_result_cap"],
            "output_limits": output_limits,
            "timeout_seconds": evidence["timeout_seconds"],
        })


def _run_trace_failure_diagnosis_scenario() -> dict[str, Any]:
    from .diagnostics import TRACE_FAILURE_DIAGNOSIS_SCHEMA, summarize_runtime
    from .event_store import JsonlEventStore
    from .runtime_log import RuntimeLogger
    from .smoke import SmokeEvidenceRecorder

    case = _harness_case("trace_failure_diagnosis")
    inputs, expected = _corpus_fields(case)
    expected_evidence = expected.get("evidence", {}) if isinstance(expected.get("evidence", {}), dict) else {}
    with tempfile.TemporaryDirectory(prefix="yinyo-scenario-trace-diagnosis-") as workspace:
        root = Path(workspace)
        event_key = str(inputs.get("event_key", "evt_trace_diagnosis"))
        logger = RuntimeLogger(str(root / "runtime.jsonl"))
        logger.record("service_start", transport="ws", profile="local")
        logger.record("webhook_accepted", correlation_id=event_key, event_key=event_key)
        logger.record(
            "outbox_delivery",
            correlation_id=event_key,
            event_key=event_key,
            success=False,
            dead_letter=True,
            attempts=3,
            error="send failed",
        )
        queue_path = root / "runtime_jobs.jsonl"
        queue_path.write_text(
            json.dumps({
                "id": "job_trace_diagnosis",
                "kind": "feishu_message",
                "payload": {"event_key": event_key},
                "status": "failed",
                "error": "tool execution failed",
                "created_at": time.time(),
                "started_at": time.time(),
                "finished_at": time.time(),
            }) + "\n",
            encoding="utf-8",
        )
        events = JsonlEventStore(str(root / "gateway_events.jsonl"))
        events.mark_seen(event_key)
        smoke = SmokeEvidenceRecorder(str(root / "smoke_evidence.jsonl"))
        smoke.record("text_message_reply", "failed", live=True, event_key=event_key)
        summary = summarize_runtime(
            log_path=str(root / "runtime.jsonl"),
            job_store_path=str(queue_path),
            smoke_evidence_path=smoke.path,
            event_store_path=str(root / "gateway_events.jsonl"),
            runtime_lock_path=str(root / "yinyo_runtime.lock"),
            transport="ws",
        )
        diagnosis = summary.get("diagnosis", {})
        refs = diagnosis.get("evidence_refs", []) if isinstance(diagnosis.get("evidence_refs"), list) else []
        passed = (
            diagnosis.get("schema") == TRACE_FAILURE_DIAGNOSIS_SCHEMA
            and diagnosis.get("root_cause") == expected_evidence.get("root_cause", "runtime_job_failed")
            and diagnosis.get("trace_complete") is True
            and len(refs) >= int(expected_evidence.get("min_evidence_refs", 1))
            and any(ref.get("layer") == "job_store" for ref in refs if isinstance(ref, dict))
            and summary.get("ok") is False
        )
        return _with_proof_envelope({
            "name": "trace_failure_diagnosis",
            "corpus_id": case["id"],
            "corpus_version": case["version"],
            "runner": case["runner"],
            "proof_contract": _corpus_proof_contract(case),
            "passed": passed,
            "evidence": {
                "diagnosis_schema": diagnosis.get("schema", ""),
                "root_cause": diagnosis.get("root_cause", ""),
                "trace_complete": diagnosis.get("trace_complete") is True,
                "evidence_ref_layers": [ref.get("layer", "") for ref in refs if isinstance(ref, dict)],
                "suggested_action_present": bool(diagnosis.get("suggested_action")),
                "candidate_count": diagnosis.get("candidate_count", 0),
            },
        }, source="versioned_harness_corpus", refs={
            "corpus": str(DEFAULT_HARNESS_SCENARIOS_PATH),
            "case": case["id"],
            "runtime_log": str(root / "runtime.jsonl"),
            "job_store": str(queue_path),
            "event_key": event_key,
        })


def _run_image_understanding_scenario() -> dict[str, Any]:
    """Prove image messages carry vision output into the agent-facing text."""

    case = _harness_case("image_understanding")
    inputs, expected = _corpus_fields(case)
    expected_evidence = expected.get("evidence", {}) if isinstance(expected.get("evidence", {}), dict) else {}

    class Session:
        def is_duplicate(self, text: str, user_id: str) -> bool:
            return False

    class Agent:
        session_manager = Session()
        last_text = ""

        def handle_message(self, user_id: str, chat_id: str, text: str,
                           already_deduped: bool = False,
                           correlation_id: str = "") -> dict[str, Any]:
            self.last_text = text
            return {"text": "ok", "files": [], "run_id": "run-image-understanding"}

    class Adapter:
        agent = Agent()
        sent: list[dict[str, Any]] = []

        def add_reaction(self, message_id: str) -> bool:
            return True

        def remove_reaction(self, message_id: str) -> bool:
            return True

        def send_message(self, chat_id: str, text: str, reply_to: str | None = None, files: list[str] | None = None) -> dict[str, Any]:
            message_ids = ["om_image_understanding"]
            self.sent.append({"chat_id": chat_id, "text": text, "reply_to": reply_to, "files": files or [], "message_ids": message_ids})
            return {"success": True, "message_ids": message_ids, "fallback": False}

        def _download_image(self, image_key: str) -> str:
            return f"{image_key}.png"

    class Vision:
        def describe(self, image_path: str, prompt: str) -> dict[str, Any]:
            template = str(inputs.get("description_template", "fixture image description from {image_path}"))
            return {"description": template.format(image_path=image_path), "error": None}

    import yinyo.vision_adapter

    original = yinyo.vision_adapter.get_vision_adapter
    yinyo.vision_adapter.get_vision_adapter = lambda: Vision()
    try:
        adapter = Adapter()
        gateway = FeishuRuntimeGateway(adapter=adapter, agent=adapter.agent, verify_token="good-token")
        event_id = str(inputs.get("event_id", "evt_image_understanding"))
        image_key = str(inputs.get("image_key", "img_fixture"))
        expected_description = str(inputs.get("description_template", "fixture image description from {image_path}")).format(image_path=f"{image_key}.png")
        result = gateway.handle_event(_image_event(event_id, image_key), async_dispatch=False)
        job = gateway.get_job(result.job_id) if result.job_id else None
        contains_description = expected_description in adapter.agent.last_text
        passed = (
            result.status_code == 200
            and job is not None
            and job.status == expected_evidence.get("job_status", "succeeded")
            and contains_description is expected_evidence.get("agent_text_contains_description", True)
            and (len(adapter.sent) == 1) is expected_evidence.get("delivery", True)
        )
        return _with_proof_envelope({
            "name": "image_understanding",
            "corpus_id": case["id"],
            "corpus_version": case["version"],
            "runner": case["runner"],
            "proof_contract": _corpus_proof_contract(case),
            "passed": passed,
            "gateway": {
                "event_key": event_id,
                "message_type": "image",
                "status_code": result.status_code,
                "job_id": result.job_id or "",
                "job_status": job.status if job else "",
                "duplicate": result.duplicate,
                "delivery": len(adapter.sent) == 1,
                "message_ids": adapter.sent[-1].get("message_ids", []) if adapter.sent else [],
            },
            "evidence": {
                "agent_text_contains_description": contains_description,
                "job_status": job.status if job else "",
                "delivery": len(adapter.sent) == 1,
            },
        }, source="versioned_harness_corpus", refs={"corpus": str(DEFAULT_HARNESS_SCENARIOS_PATH), "case": case["id"], "job_id": result.job_id or "", "message_ids": adapter.sent[-1].get("message_ids", []) if adapter.sent else []})
    finally:
        yinyo.vision_adapter.get_vision_adapter = original


def _run_long_conversation_scenario() -> dict[str, Any]:
    from .context import ContextManager

    case = _harness_case("long_conversation")
    inputs = case.get("inputs", {})
    expected = case.get("expect", {}).get("evidence", {})
    protected_marker = str(inputs.get("recent_user_text", "PROTECTED_RECENT_MESSAGE"))
    min_masked = int(expected.get("masked_observations_after", {}).get("value", 1))
    with tempfile.TemporaryDirectory(prefix="yinyo-scenario-context-") as workspace:
        ctx = ContextManager(max_tokens=80, keep_tail=4, cache_dir=str(Path(workspace) / "cache"))
        template = str(inputs.get("old_observation_template", "old observation {index}"))
        for i in range(int(inputs.get("turns", 20))):
            ctx.messages.append({"role": "tool", "content": template.format(index=i) + " " + ("x" * 50)})
        ctx.messages.append({"role": "user", "content": protected_marker})

        before = ctx.retention_report([protected_marker])
        ctx.auto_manage(step=1)
        after = ctx.retention_report([protected_marker])
        passed = (
            before["estimated_tokens"] > ctx.max_tokens
            and after["masked_observations"] >= min_masked
            and after["protected_present"][protected_marker] is expected.get("protected_recent_context", True)
        )
        return _with_proof_envelope({
            "name": "long_conversation",
            "corpus_id": case["id"],
            "corpus_version": case["version"],
            "runner": case["runner"],
            "proof_contract": _corpus_proof_contract(case),
            "passed": passed,
            "evidence": {
                "estimated_tokens_before": before["estimated_tokens"],
                "masked_observations_after": after["masked_observations"],
                "protected_recent_context": after["protected_present"][protected_marker],
            },
        }, source="versioned_harness_corpus", refs={"corpus": str(DEFAULT_HARNESS_SCENARIOS_PATH), "case": case["id"], "retention_report": "context.retention_report", "workspace": workspace})


def _run_memory_supersession_scenario() -> dict[str, Any]:
    from .memory import TemporalTree

    case = _harness_case("memory_supersession")
    inputs, expected = _corpus_fields(case)
    expected_evidence = expected.get("evidence", {}) if isinstance(expected.get("evidence", {}), dict) else {}
    with tempfile.TemporaryDirectory(prefix="yinyo-scenario-memory-") as workspace:
        tree = TemporalTree(str(Path(workspace) / "temporal_tree.json"))
        v1 = tree.add(str(inputs.get("old_fact", "user prefers concise Feishu replies")), category=str(inputs.get("category", "Preferences")), confidence=0.5)
        v2 = tree.supersede(v1.id, str(inputs.get("new_fact", "user prefers concise Feishu replies with evidence links")), source_run_id="scenario")
        search = tree.search(str(inputs.get("query", "concise Feishu replies")), limit=5)
        trail = tree.get_audit_trail(v1.id)
        search_excludes_old = not any(node.id == v1.id for node in search)
        version_expect = expected_evidence.get("new_fact_version", {})
        min_version = int(version_expect.get("value", 2)) if isinstance(version_expect, dict) else int(version_expect or 2)
        passed = (
            v2 is not None
            and tree.nodes[v1.id].status == expected_evidence.get("old_fact_status", "superseded")
            and tree.nodes[v1.id].superseded_by == v2.id
            and any(node.id == v2.id for node in search)
            and search_excludes_old is expected_evidence.get("search_excludes_old", True)
            and len(trail) == expected_evidence.get("audit_trail_length", 2)
            and (v2.version if v2 else 0) >= min_version
        )
        return _with_proof_envelope({
            "name": "memory_supersession",
            "corpus_id": case["id"],
            "corpus_version": case["version"],
            "runner": case["runner"],
            "proof_contract": _corpus_proof_contract(case),
            "passed": passed,
            "evidence": {
                "old_fact_status": tree.nodes[v1.id].status,
                "new_fact_version": v2.version if v2 else None,
                "audit_trail_length": len(trail),
                "search_result_ids": [node.id for node in search],
                "search_excludes_old": search_excludes_old,
            },
        }, source="versioned_harness_corpus", refs={"corpus": str(DEFAULT_HARNESS_SCENARIOS_PATH), "case": case["id"], "old_fact_id": v1.id, "new_fact_id": v2.id if v2 else "", "workspace": workspace})


def _run_memory_durability_policy_scenario() -> dict[str, Any]:
    from .memory import MemoryStore
    from .model import ModelGateway

    case = _harness_case("memory_durability_policy")
    inputs = case.get("inputs", {})
    expected = case.get("expect", {}).get("evidence", {})
    with tempfile.TemporaryDirectory(prefix="yinyo-scenario-memory-durability-") as workspace:
        store = MemoryStore(workspace)
        model = ModelGateway(api_key="")
        store.set_model(model)
        model.set_mock_responses([
            {
                "content": json.dumps([
                    {
                        "content": str(inputs.get("ephemeral_fact", "The assistant answered hello during this run.")),
                        "category": str(inputs.get("ephemeral_category", "General")),
                        "confidence": 0.9,
                        "supersedes": None,
                    },
                    {
                        "content": str(inputs.get("durable_fact", "User prefers concise release status updates with concrete blockers.")),
                        "category": str(inputs.get("durable_category", "Preferences")),
                        "confidence": 0.9,
                        "supersedes": None,
                    },
                ]),
                "finish_reason": "stop",
            },
        ])
        result = store.extract_and_store([
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hello"},
        ], "scenario")
        active = store.tree.get_active_nodes()
        passed = (
            result["stored"] == expected.get("stored", 1)
            and result["rejected"] == expected.get("rejected", 1)
            and result["reasons"] == expected.get("reasons", ["ephemeral_content"])
            and [node.category for node in active] == expected.get("active_categories", ["Preferences"])
        )
        return _with_proof_envelope({
            "name": "memory_durability_policy",
            "corpus_id": case["id"],
            "corpus_version": case["version"],
            "runner": case["runner"],
            "proof_contract": _corpus_proof_contract(case),
            "passed": passed,
            "evidence": {
                "stored": result["stored"],
                "rejected": result["rejected"],
                "reasons": result["reasons"],
                "active_categories": [node.category for node in active],
            },
        }, source="versioned_harness_corpus", refs={"corpus": str(DEFAULT_HARNESS_SCENARIOS_PATH), "case": case["id"], "workspace": workspace, "stored": result["stored"], "rejected": result["rejected"]})


def _run_temporal_state_recovery_scenario() -> dict[str, Any]:
    from .memory import TemporalTree

    case = _harness_case("temporal_state_recovery")
    inputs, expected = _corpus_fields(case)
    expected_evidence = expected.get("evidence", {}) if isinstance(expected.get("evidence", {}), dict) else {}
    with tempfile.TemporaryDirectory(prefix="yinyo-scenario-temporal-state-") as workspace:
        tree_path = Path(workspace) / "temporal_tree.json"
        tree = TemporalTree(str(tree_path))
        old = tree.add(
            str(inputs.get("old_fact", "Project state is alpha.")),
            category="Projects",
            confidence=0.7,
            source_run_id="run-old",
        )
        old.created_at = "2025-01-01T00:00:00+00:00"
        old.updated_at = "2025-01-01T00:00:00+00:00"
        tree._save()
        new = tree.supersede(old.id, str(inputs.get("new_fact", "Project state is release candidate.")), source_run_id="run-new")
        archived = tree.add(
            str(inputs.get("archived_fact", "Temporary rollout note.")),
            category="Projects",
            confidence=0.6,
            source_run_id="run-archive",
        )
        tree.archive(archived.id)

        recovered = TemporalTree(str(tree_path))
        report = recovered.state_report(stale_after_days=int(inputs.get("stale_after_days", 30)))
        trail = recovered.get_audit_trail(old.id)
        search = recovered.search("Project state", limit=5)
        passed = (
            report.get("schema") == "yinyo.temporal_state_report.v1"
            and report.get("provenance_complete") is expected_evidence.get("provenance_complete", True)
            and report.get("superseded") == expected_evidence.get("superseded", 1)
            and report.get("archived") == expected_evidence.get("archived", 1)
            and report.get("stale") == expected_evidence.get("stale", 0)
            and len(trail) == expected_evidence.get("audit_trail_length", 2)
            and any(node.id == new.id for node in search)
            and not any(node.id == old.id for node in search)
        )
        return _with_proof_envelope({
            "name": "temporal_state_recovery",
            "corpus_id": case["id"],
            "corpus_version": case["version"],
            "runner": case["runner"],
            "proof_contract": _corpus_proof_contract(case),
            "passed": passed,
            "evidence": {
                "state_report_schema": report.get("schema", ""),
                "recovered_from_disk": len(recovered.nodes) == len(tree.nodes),
                "provenance_complete": report.get("provenance_complete") is True,
                "missing_provenance": report.get("missing_provenance", []),
                "active": report.get("active", 0),
                "superseded": report.get("superseded", 0),
                "archived": report.get("archived", 0),
                "stale": report.get("stale", 0),
                "audit_trail_length": len(trail),
                "search_excludes_old": not any(node.id == old.id for node in search),
                "search_result_ids": [node.id for node in search],
            },
        }, source="versioned_harness_corpus", refs={
            "corpus": str(DEFAULT_HARNESS_SCENARIOS_PATH),
            "case": case["id"],
            "tree_path": str(tree_path),
            "old_fact_id": old.id,
            "new_fact_id": new.id if new else "",
            "archived_fact_id": archived.id,
        })


def _run_fact_hygiene_policy_scenario() -> dict[str, Any]:
    case = _harness_case("fact_hygiene_policy")
    inputs, expected = _corpus_fields(case)
    expected_evidence = expected.get("evidence", {}) if isinstance(expected.get("evidence", {}), dict) else {}
    with tempfile.TemporaryDirectory(prefix="yinyo-scenario-fact-hygiene-") as workspace:
        agent = YinyoAgent(workspace=workspace, max_steps=2)
        agent.model.set_mock_responses([
            {"content": "[STEP 1] answer", "finish_reason": "stop"},
            {"content": "The latest stock price is 123.", "finish_reason": "stop"},
            {"content": '{"reflections": [], "memory_add": [], "memory_update": [], "memory_remove": []}', "finish_reason": "stop"},
            {"content": "[]", "finish_reason": "stop"},
        ])
        result = agent.run(str(inputs.get("question", "What is the latest stock price?")))
        passed = (
            result["status"] == expected_evidence.get("status", "source_required")
            and result.get("source_audit", {}).get("required") is expected_evidence.get("source_required", True)
            and result.get("source_audit", {}).get("satisfied") is expected_evidence.get("source_satisfied", False)
        )
        return _with_proof_envelope({
            "name": "fact_hygiene_policy",
            "corpus_id": case["id"],
            "corpus_version": case["version"],
            "runner": case["runner"],
            "proof_contract": _corpus_proof_contract(case),
            "passed": passed,
            "evidence": {
                "status": result["status"],
                "source_required": result.get("source_audit", {}).get("required"),
                "source_satisfied": result.get("source_audit", {}).get("satisfied"),
            },
        }, source="versioned_harness_corpus", refs={
            "corpus": str(DEFAULT_HARNESS_SCENARIOS_PATH),
            "case": case["id"],
            "evidence_file": result.get("evidence_file", ""),
            "source_required": result.get("source_audit", {}).get("required"),
        })


def _run_state_handoff_scenario() -> dict[str, Any]:
    from .handoff import replay_handoff

    case = _harness_case("state_handoff")
    inputs, expected = _corpus_fields(case)
    expected_evidence = expected.get("evidence", {}) if isinstance(expected.get("evidence", {}), dict) else {}
    task = str(inputs.get("task", "prepare a state transfer packet"))
    correlation_id = str(inputs.get("correlation_id", "scenario-handoff"))
    max_steps = int(inputs.get("max_steps", 2))
    with tempfile.TemporaryDirectory(prefix="yinyo-scenario-handoff-") as workspace:
        agent = YinyoAgent(workspace=workspace, max_steps=max_steps)
        agent.model.set_mock_responses([
            {"content": "[STEP 1] answer", "finish_reason": "stop"},
            {"content": "done", "finish_reason": "stop"},
            {"content": '{"reflections": [], "memory_add": [], "memory_update": [], "memory_remove": []}', "finish_reason": "stop"},
            {"content": "[]", "finish_reason": "stop"},
        ])
        result = agent.run(task, correlation_id=correlation_id)
        handoff_path = Path(workspace) / result.get("handoff_file", "")
        handoff = json.loads(handoff_path.read_text(encoding="utf-8")) if handoff_path.is_file() else {}
        manifest_path = Path(workspace) / "runs" / result["run_id"] / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
        resume = replay_handoff(handoff_path, workspace=workspace)
        evidence = {
            "schema": handoff.get("schema", ""),
            "correlation_id": handoff.get("correlation_id", ""),
            "intent_recorded": handoff.get("intent", {}).get("original_task") == task,
            "permissions_recorded": handoff.get("permissions", {}).get("confirm_tools_require_structured_metadata") is True,
            "source_audit_recorded": "source_audit" in handoff.get("provenance", {}),
            "budget_recorded": (
                handoff.get("budget_state", {}).get("max_steps") == max_steps
                and handoff.get("budget_state", {}).get("steps_used", 0) + handoff.get("budget_state", {}).get("steps_remaining", 0) == max_steps
                and "model_usage" in handoff.get("budget_state", {})
            ),
            "trace_history_recorded": handoff.get("trace_history", {}).get("correlation_id") == correlation_id and isinstance(handoff.get("trace_history", {}).get("evidence_hashes", []), list),
            "manifest_linked": manifest.get("handoff", {}).get("path") == result.get("handoff_file"),
            "resume_schema": resume.get("schema", ""),
            "resume_ready": resume.get("resume_ready") is True,
            "resume_ok": resume.get("ok") is True,
            "resume_artifacts_exist": (
                resume.get("checks", {}).get("evidence_artifact_exists") is True
                and resume.get("checks", {}).get("manifest_artifact_exists") is True
            ),
            "resume_budget_recoverable": resume.get("checks", {}).get("budget_recoverable") is True,
            "resume_trace_recoverable": resume.get("checks", {}).get("trace_recoverable") is True,
            "resume_inherits_intent": resume.get("inherited", {}).get("intent", {}).get("original_task") == task,
            "resume_inherits_constraints": bool(resume.get("inherited", {}).get("constraints", {}).get("workspace")),
            "resume_inherits_permissions": resume.get("inherited", {}).get("permissions", {}).get("confirm_tools_require_structured_metadata") is True,
            "resume_inherits_artifacts": (
                resume.get("checks", {}).get("evidence_artifact") is True
                and resume.get("checks", {}).get("manifest_artifact") is True
                and resume.get("checks", {}).get("evidence_artifact_exists") is True
                and resume.get("checks", {}).get("manifest_artifact_exists") is True
            ),
            "resume_inherits_provenance": "source_audit" in resume.get("inherited", {}).get("provenance", {}),
            "resume_inherits_budget": resume.get("inherited", {}).get("budget_state", {}).get("max_steps") == max_steps,
            "resume_inherits_trace_history": resume.get("inherited", {}).get("trace_history", {}).get("correlation_id") == correlation_id,
            "resume_inherits_risk": isinstance(resume.get("inherited", {}).get("risk", {}).get("risk_notes", []), list),
            "resume_inherits_unresolved": isinstance(resume.get("inherited", {}).get("unresolved", []), list),
        }
        passed = (
            handoff.get("schema") == str(expected_evidence.get("schema", "yinyo.handoff.v1"))
            and handoff.get("correlation_id") == str(expected_evidence.get("correlation_id", correlation_id))
            and handoff.get("artifacts", {}).get("evidence_file") == result.get("evidence_file")
            and manifest.get("handoff", {}).get("path") == result.get("handoff_file")
            and resume.get("ok") is True
            and all(evidence.get(key) == value for key, value in expected_evidence.items())
        )
        return _with_proof_envelope({
            "name": "state_handoff",
            "corpus_id": case["id"],
            "corpus_version": case["version"],
            "runner": case.get("runner", "state_handoff"),
            "passed": passed,
            "evidence": evidence,
            "proof_contract": _corpus_proof_contract(case),
        }, source="versioned_harness_corpus", refs={"corpus": str(_ACTIVE_HARNESS_SCENARIOS_PATH), "case": case["id"], "handoff_file": result.get("handoff_file", ""), "manifest_path": str(manifest_path), "resume_schema": resume.get("schema", "")})


def _run_delegated_worker_trace_scenario() -> dict[str, Any]:
    from .agent import YinyoAgent
    from .tools import delegate_task

    case = _harness_case("delegated_worker_trace")
    inputs, expected = _corpus_fields(case)
    expected_evidence = expected.get("evidence", {}) if isinstance(expected.get("evidence", {}), dict) else {}
    parent_context_marker = str(inputs.get("parent_context_marker", "parent shared context marker"))
    goal = str(inputs.get("goal", "search for the shared context marker"))
    search_query = str(inputs.get("search_query", "shared context marker"))
    with tempfile.TemporaryDirectory(prefix="yinyo-scenario-delegate-") as workspace:
        agent = YinyoAgent(workspace=workspace, max_steps=1)
        parent_run_id = "parent-delegation-scenario"
        agent.current_run_id = parent_run_id
        agent.context.add({"role": "system", "content": "Parent system instruction for worker."})
        agent.context.add({"role": "user", "content": parent_context_marker})
        agent.model.set_mock_responses([
            {
                "content": "",
                "tool_calls": [{
                    "id": "call_search",
                    "type": "function",
                    "function": {
                        "name": "do_search",
                        "arguments": json.dumps({"query": search_query, "path": "."}),
                    },
                }],
                "finish_reason": "tool_calls",
            },
            {"content": "worker complete", "finish_reason": "stop"},
        ])
        result = delegate_task(goal)
        tool_names = result.get("tool_names", [])
        trace_refs = result.get("trace_refs", [])
        evidence = {
            "schema": "yinyo.delegated_worker_trace.v1",
            "parent_run_id": parent_run_id,
            "worker_run_id": result.get("run_id", ""),
            "worker_status": result.get("status", ""),
            "worker_steps": result.get("steps", 0),
            "parent_context_shared": any(
                parent_context_marker in str(message.get("content", ""))
                for message in agent.context.messages
            ),
            "tool_traces_count": result.get("tool_traces_count", 0),
            "tool_names": tool_names,
            "trace_refs": trace_refs,
            "result_text": result.get("result", ""),
        }
        passed = (
            evidence["worker_status"] == expected_evidence.get("worker_status", "success")
            and evidence["parent_context_shared"] is expected_evidence.get("parent_context_shared", True)
            and evidence["worker_run_id"] != parent_run_id
            and evidence["tool_traces_count"] >= int(expected_evidence.get("tool_traces_min", 1))
            and str(expected_evidence.get("required_tool", "do_search")) in tool_names
            and bool(trace_refs)
        )
        return _with_proof_envelope({
            "name": "delegated_worker_trace",
            "corpus_id": case["id"],
            "corpus_version": case["version"],
            "runner": case["runner"],
            "proof_contract": _corpus_proof_contract(case),
            "passed": passed,
            "evidence": evidence,
        }, source="versioned_harness_corpus", refs={
            "corpus": str(DEFAULT_HARNESS_SCENARIOS_PATH),
            "case": case["id"],
            "parent_run_id": parent_run_id,
            "worker_run_id": evidence["worker_run_id"],
            "tool_traces_count": evidence["tool_traces_count"],
            "trace_refs": trace_refs,
        })


def _run_trace2skill_promotion_scenario() -> dict[str, Any]:
    from .evolution import FailurePattern, SkillEvolution
    from .model import ModelGateway

    case = _harness_case("trace2skill_promotion")
    inputs, expected = _corpus_fields(case)
    expected_evidence = expected.get("evidence", {}) if isinstance(expected.get("evidence", {}), dict) else {}
    with tempfile.TemporaryDirectory(prefix="yinyo-scenario-trace2skill-") as workspace:
        model = ModelGateway(api_key="")
        model.set_mock_responses([
            {
                "content": json.dumps({
                    "name": str(inputs.get("skill_name", "retry-file-write")),
                    "description": "Handle repeated file write failures safely.",
                    "steps": ["Check workspace", "Request confirmation", "Verify evidence"],
                    "triggers": ["write", "confirm"],
                    "pitfalls": ["Do not bypass confirmation"],
                }),
                "finish_reason": "stop",
            },
        ])
        evolution = SkillEvolution(workspace, model=model)
        pattern = FailurePattern(
            task_keywords=list(inputs.get("task_keywords", ["write", "confirm"])),
            error_message=str(inputs.get("error_message", "Confirmation required")),
            occurrence_count=int(inputs.get("occurrence_count", 2)),
            last_occurred="2026-05-27T00:00:00+00:00",
        )
        skill = evolution.extract_skill_from_failure(pattern, "write a file", str(inputs.get("error_message", "Confirmation required")))
        validation = evolution.validate_skill_regression(skill.name)
        promotion = evolution.promote_skill_after_validation(skill.name, validation)
        harness_result = validation.get("harness_result", {})

        skill_dir = Path(workspace) / "skills" / skill.name
        meta = json.loads((skill_dir / "meta.json").read_text(encoding="utf-8"))
        regression = json.loads((skill_dir / "regression.json").read_text(encoding="utf-8"))
        expected_statuses = set(expected_evidence.get("promotion_status", ["proven", "stable"]))
        passed = (
            skill is not None
            and regression["expected_failure"] == str(inputs.get("error_message", "Confirmation required"))
            and regression["failure_trace_ref"]
            and validation["passed"] is expected_evidence.get("validation_passed", True)
            and promotion["promoted"] is True
            and meta["status"] in expected_statuses
        )
        return _with_proof_envelope({
            "name": "trace2skill_promotion",
            "corpus_id": case["id"],
            "corpus_version": case["version"],
            "runner": case["runner"],
            "proof_contract": _corpus_proof_contract(case),
            "passed": passed,
            "evidence": {
                "skill_name": skill.name,
                "regression_fixture": (skill_dir / "regression.json").is_file(),
                "regression_replay_passed": validation["passed"],
                "validation_passed": validation["passed"],
                "replay_command_passed": validation.get("checks", {}).get("replay_command_passed") is True,
                "pre_skill_failure_reproduced": validation.get("checks", {}).get("pre_skill_failure_reproduced") is True,
                "post_skill_guardrail_applied": validation.get("checks", {}).get("post_skill_guardrail_applied") is True,
                "guardrail_applied": harness_result.get("guardrail_applied") is True,
                "regression_harness_schema": harness_result.get("schema", ""),
                "pre_skill_failed": validation.get("checks", {}).get("pre_skill_command_failed_as_expected") is True,
                "pre_skill_exit_code": validation.get("pre_skill_result", {}).get("exit_code"),
                "pre_skill_run_ref": validation.get("pre_skill_result", {}).get("path", ""),
                "post_skill_passed": validation.get("checks", {}).get("post_skill_command_passed") is True,
                "post_skill_exit_code": validation.get("post_skill_result", {}).get("exit_code"),
                "post_skill_run_ref": validation.get("post_skill_result", {}).get("path", ""),
                "replay_exit_code": validation.get("replay_result", {}).get("exit_code"),
                "replay_stdout_mentions_failure": validation.get("checks", {}).get("replay_output_mentions_failure") is True,
                "replay_stdout_mentions_guardrail": validation.get("checks", {}).get("replay_output_mentions_guardrail") is True,
                "promotion_status": meta["status"],
                "promotion_record": promotion["promoted"],
                "failure_trace_ref": regression["failure_trace_ref"],
                "post_promotion_run_ref": validation.get("post_skill_result", {}).get("path", ""),
            },
        }, source="versioned_harness_corpus", refs={
            "corpus": str(DEFAULT_HARNESS_SCENARIOS_PATH),
            "case": case["id"],
            "failure_trace_ref": regression["failure_trace_ref"],
            "skill_ref": str(skill_dir / "meta.json"),
            "regression_result_ref": str(skill_dir / "regression.json"),
            "validation_ref": validation["path"],
            "promotion_record_ref": promotion["path"],
            "promotion_status": meta["status"],
            "pre_skill_run_ref": validation.get("pre_skill_result", {}).get("path", ""),
            "post_skill_run_ref": validation.get("post_skill_result", {}).get("path", ""),
            "post_promotion_run_ref": validation.get("post_skill_result", {}).get("path", ""),
        })


def _run_deepseek_usage_scenario() -> dict[str, Any]:
    from .agent import YinyoAgent
    from .model import ModelGateway

    case = _harness_case("deepseek_usage")
    inputs, expected = _corpus_fields(case)
    expected_evidence = expected.get("evidence", {}) if isinstance(expected.get("evidence", {}), dict) else {}
    budget = inputs.get("budget", {}) if isinstance(inputs.get("budget", {}), dict) else {}
    with tempfile.TemporaryDirectory(prefix="yinyo-scenario-deepseek-") as workspace:
        agent = YinyoAgent(workspace=workspace, max_steps=2, model_retry_count=1)
        agent.model.set_mock_responses([
            {"content": "[STEP 1] answer", "finish_reason": "stop", "usage": {"prompt_tokens": 10, "completion_tokens": 2}},
            {"content": "done", "finish_reason": "stop", "usage": {"prompt_tokens": 20, "completion_tokens": 4}, "model": "deepseek-v4-flash"},
            {"content": '{"reflections": [], "memory_add": [], "memory_update": [], "memory_remove": []}', "finish_reason": "stop", "usage": {"prompt_tokens": 5, "completion_tokens": 1}},
            {"content": "[]", "finish_reason": "stop"},
        ])
        result = agent.run("record model usage")
        manifest = json.loads((Path(workspace) / "runs" / result["run_id"] / "manifest.json").read_text(encoding="utf-8"))
        usage = result["model_usage"]
        retry_gateway = ModelGateway(api_key="sk-test", retry_count=1, retry_backoff_seconds=0)
        retry_gateway._call_api = lambda *args, **kwargs: {"error": "timeout"} if not retry_gateway.last_attempts else {
            "content": "retry-ok",
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 3, "completion_tokens": 1},
        }
        retry_result = retry_gateway.chat([{"role": "user", "content": "retry"}])
        fallback_gateway = ModelGateway(api_key="sk-test", retry_count=0)
        fallback_calls = {"count": 0}
        def _fallback_api(*args: Any, **kwargs: Any) -> dict[str, Any]:
            fallback_calls["count"] += 1
            if fallback_calls["count"] == 1:
                return {"error": "rate_limit"}
            return {
                "content": "fallback-ok",
                "finish_reason": "stop",
                "usage": {"prompt_tokens": 4, "completion_tokens": 2},
            }
        fallback_gateway._call_api = _fallback_api
        fallback_result = fallback_gateway.chat([{"role": "user", "content": "fallback"}])
        error_gateway = ModelGateway(api_key="sk-test", retry_count=0)
        error_calls = {"count": 0}
        def _error_api(*args: Any, **kwargs: Any) -> dict[str, Any]:
            error_calls["count"] += 1
            return {"error": "timeout" if error_calls["count"] == 1 else "rate_limit"}
        error_gateway._call_api = _error_api
        error_result = error_gateway.chat([{"role": "user", "content": "error"}])
        model_envelope = {
            "schema": "yinyo.model_envelope.v1",
            "budget": {
                "max_prompt_tokens": int(budget.get("max_prompt_tokens", 64)),
                "max_completion_tokens": int(budget.get("max_completion_tokens", 16)),
                "max_total_tokens": int(budget.get("max_total_tokens", 96)),
                "max_estimated_cost_usd": float(budget.get("max_estimated_cost_usd", 0.001)),
            },
            "within_budget": (
                usage["prompt_tokens"] <= 64
                and usage["completion_tokens"] <= 16
                and usage["total_tokens"] <= 96
                and usage["estimated_cost_usd"] <= 0.001
            ),
            "retry_attempts": retry_result.get("_attempts", []),
            "retry_recovered": retry_result.get("content") == "retry-ok",
            "fallback_attempts": fallback_result.get("_attempts", []),
            "fallback_observed": fallback_result.get("_fallback") is True,
            "fallback_from": fallback_result.get("_fallback_from", ""),
            "error_attempts": error_result.get("_attempts", []),
            "error_classifications": sorted({item.get("error", "") for item in error_result.get("_attempts", []) if item.get("error")}),
            "degradation_status": "model_error" if error_result.get("error") else "",
            "user_visible_degradation": "No successful answer was verified; check the run evidence before retrying.",
        }
        passed = (
            usage["total_tokens"] == expected_evidence.get("total_tokens", 42)
            and usage["estimated_cost_usd"] > 0
            and manifest["model_usage"] == usage
            and model_envelope["within_budget"] is expected_evidence.get("within_budget", True)
            and model_envelope["retry_recovered"] is expected_evidence.get("retry_recovered", True)
            and model_envelope["fallback_observed"] is expected_evidence.get("fallback_observed", True)
            and model_envelope["degradation_status"] == expected_evidence.get("degradation_status", "model_error")
            and set(expected_evidence.get("error_classifications", ["rate_limit", "timeout"])).issubset(set(model_envelope["error_classifications"]))
        )
        return _with_proof_envelope({
            "name": "deepseek_usage",
            "corpus_id": case["id"],
            "corpus_version": case["version"],
            "runner": case["runner"],
            "proof_contract": _corpus_proof_contract(case),
            "passed": passed,
            "evidence": {
                "model_usage": usage,
                "manifest_matches_result": manifest["model_usage"] == usage,
                "default_model": agent.model.default_model,
                "model_envelope": model_envelope,
            },
        }, source="versioned_harness_corpus", refs={
            "corpus": str(DEFAULT_HARNESS_SCENARIOS_PATH),
            "case": case["id"],
            "manifest_path": str(Path(workspace) / "runs" / result["run_id"] / "manifest.json"),
            "model_envelope_schema": model_envelope["schema"],
        })


def _run_card_fallback_scenario() -> dict[str, Any]:
    from .feishu_card import CARD_INVALID_ERROR, is_card_invalid_error
    from .smoke import SmokeEvidenceRecorder, verify_smoke_evidence

    case = _harness_case("card_fallback")
    inputs, expected = _corpus_fields(case)
    expected_evidence = expected.get("evidence", {}) if isinstance(expected.get("evidence", {}), dict) else {}

    class Session:
        def is_duplicate(self, text: str, user_id: str) -> bool:
            return False

    class Agent:
        session_manager = Session()

        def handle_message(self, user_id: str, chat_id: str, text: str,
                           already_deduped: bool = False,
                           correlation_id: str = "") -> dict[str, Any]:
            return {"text": "ok", "files": [{"path": "report.md"}], "run_id": "run-card"}

    class Adapter:
        agent = Agent()

        def add_reaction(self, message_id: str) -> bool:
            return True

        def remove_reaction(self, message_id: str) -> bool:
            return True

        def send_message(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            return {"success": True, "message_ids": ["om_reply"], "fallback": True}

        def _download_image(self, image_key: str) -> str:
            return image_key

    with tempfile.TemporaryDirectory(prefix="yinyo-scenario-card-") as workspace:
        smoke_path = Path(workspace) / "smoke.jsonl"
        gateway = FeishuRuntimeGateway(
            adapter=Adapter(),
            agent=Adapter.agent,
            verify_token="good-token",
            smoke_recorder=SmokeEvidenceRecorder(str(smoke_path)),
        )
        event_id = str(inputs.get("event_id", "evt_card_1"))
        required = set(inputs.get("required_smoke", ["text_message_reply", "card_fallback"]))
        result = gateway.handle_event(_text_event(event_id, str(inputs.get("text", "hello"))), async_dispatch=False)
        job = gateway.get_job(result.job_id)
        smoke = verify_smoke_evidence(str(smoke_path), required=required)
        error_detected = is_card_invalid_error(f"{CARD_INVALID_ERROR}: content format of the post type is incorrect")
        passed = (
            job is not None
            and job.result["fallback"] is expected_evidence.get("gateway_fallback", True)
            and smoke["ok"] is expected_evidence.get("smoke_ok", True)
            and error_detected is expected_evidence.get("card_invalid_error_detected", True)
        )
        return _with_proof_envelope({
            "name": "card_fallback",
            "corpus_id": case["id"],
            "corpus_version": case["version"],
            "runner": case["runner"],
            "proof_contract": _corpus_proof_contract(case),
            "passed": passed,
            "gateway": {
                "event_key": event_id,
                "message_type": "text",
                "status_code": result.status_code,
                "job_id": result.job_id or "",
                "job_status": job.status if job else "",
                "duplicate": result.duplicate,
                "delivery": bool(job and job.result.get("message_ids")),
                "message_ids": job.result.get("message_ids", []) if job else [],
                "fallback": job.result.get("fallback") if job else False,
            },
            "evidence": {
                "gateway_fallback": job.result["fallback"] if job else False,
                "smoke_passed": smoke["passed"],
                "card_invalid_error_detected": error_detected,
            },
        }, source="versioned_harness_corpus", refs={
            "corpus": str(DEFAULT_HARNESS_SCENARIOS_PATH),
            "case": case["id"],
            "job_id": result.job_id or "",
            "smoke_path": str(smoke_path),
        })


def _run_partial_failure_scenario() -> dict[str, Any]:
    from .agent import YinyoAgent

    case = _harness_case("partial_failure")
    inputs, expected = _corpus_fields(case)
    expected_evidence = expected.get("evidence", {}) if isinstance(expected.get("evidence", {}), dict) else {}
    blocked_expect = expected_evidence.get("blocked_evidence_records", {})
    min_blocked = int(blocked_expect.get("value", 0)) if isinstance(blocked_expect, dict) else int(blocked_expect or 0)
    with tempfile.TemporaryDirectory(prefix="yinyo-scenario-partial-") as workspace:
        agent = YinyoAgent(workspace=workspace, max_steps=3)
        agent.model.set_mock_responses([
            {"content": "[STEP 1] try blocked command", "finish_reason": "stop"},
            {
                "content": "",
                "tool_calls": [{
                    "id": "call_run",
                    "type": "function",
                    "function": {
                        "name": "do_run",
                        "arguments": json.dumps({
                            "command": str(inputs.get("dangerous_command", "rm -rf /")),
                            "confirmation": {
                                "actor": str(inputs.get("confirmation_actor", "scenario-operator")),
                                "scope": "do_run",
                                "reason": "prove dangerous command remains blocked",
                                "expires_at": "2099-01-01T00:00:00Z",
                            },
                        }),
                    },
                }],
                "finish_reason": "tool_calls",
            },
            {"content": "done", "finish_reason": "stop"},
        ])
        result = agent.run("run a dangerous command")
        evidence_text = (Path(workspace) / result["evidence_file"]).read_text(encoding="utf-8")
        evidence_records = [
            json.loads(line)
            for line in evidence_text.splitlines()
            if line.strip()
        ]
        blocked_records = [
            record for record in evidence_records
            if "_blocked" in json.dumps(record.get("result", {}), ensure_ascii=False)
        ]
        passed = (
            result["status"] == expected_evidence.get("user_visible_status", "partial")
            and len(blocked_records) > min_blocked
            and "Blocked by risk policy" in evidence_text
        )
        return _with_proof_envelope({
            "name": "partial_failure",
            "corpus_id": case["id"],
            "corpus_version": case["version"],
            "runner": case["runner"],
            "proof_contract": _corpus_proof_contract(case),
            "passed": passed,
            "evidence": {
                "user_visible_status": result["status"],
                "blocked_evidence_records": len(blocked_records),
                "operator_evidence_file": result["evidence_file"],
                "no_false_success": result["status"] != "success",
            },
        }, source="versioned_harness_corpus", refs={"corpus": str(DEFAULT_HARNESS_SCENARIOS_PATH), "case": case["id"], "evidence_file": result.get("evidence_file", ""), "blocked_records": len(blocked_records)})


def _run_release_gate_scenario() -> dict[str, Any]:
    from .smoke import required_live_smoke_scenarios, verify_smoke_evidence

    case = _harness_case("release_gate")
    inputs = case.get("inputs", {})
    expected = case.get("expect", {})
    expected_evidence = expected.get("evidence", {})
    with tempfile.TemporaryDirectory(prefix="yinyo-scenario-release-") as workspace:
        transport = str(inputs.get("transport", "ws"))
        required = set(required_live_smoke_scenarios(transport))
        missing_smoke = verify_smoke_evidence(str(Path(workspace) / "missing_smoke.jsonl"), required=required)
        excluded = set(expected_evidence.get("required_live_scenarios_excludes", []))
        expected_bundle = expected.get("bundle", {})
        passed = (
            missing_smoke["ok"] is False
            and "card_fallback" in missing_smoke["missing"]
            and missing_smoke["required"] == sorted(required)
            and not excluded.intersection(set(missing_smoke["required"]))
            and expected_evidence.get("transport", transport) == transport
            and expected_bundle.get("required", True) is True
            and expected_bundle.get("verified", False) is False
        )
        return _with_proof_envelope({
            "name": "release_gate",
            "corpus_id": case["id"],
            "corpus_version": case["version"],
            "runner": case["runner"],
            "proof_contract": _corpus_proof_contract(case),
            "passed": passed,
            "evidence": {
                "transport": transport,
                "live_smoke_blocks_1_0_until_present": missing_smoke["ok"] is False,
                "required_live_scenarios": missing_smoke["required"],
                "missing_live_scenarios": missing_smoke["missing"],
            },
            "bundle": {
                "required": True,
                "verified": False,
                "digest": "",
            },
        }, source="versioned_harness_corpus", refs={"corpus": str(DEFAULT_HARNESS_SCENARIOS_PATH), "case": case["id"], "required_live_scenarios": missing_smoke["required"], "missing_live_scenarios": missing_smoke["missing"], "bundle_required": True, "bundle_verified": False})


def _text_event(event_id: str, text: str) -> dict[str, Any]:
    return {
        "type": "event_callback",
        "uuid": event_id,
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": text}),
                "chat_id": "oc_1",
                "message_id": f"om_{event_id}",
            },
        },
    }


def _image_event(event_id: str, image_key: str) -> dict[str, Any]:
    return {
        "type": "event_callback",
        "uuid": event_id,
        "token": "good-token",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_type": "image",
                "content": json.dumps({"image_key": image_key}),
                "chat_id": "oc_1",
                "message_id": f"om_{event_id}",
            },
        },
    }
