"""1.0 evidence matrix for YINYO's product cores and traits."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EvidenceRequirement:
    id: str
    claim: str
    required_scenarios: tuple[str, ...]
    live_required: tuple[str, ...]
    required_proof: tuple[str, ...]


@dataclass(frozen=True)
class HarnessLayerRequirement:
    layer: str
    claim: str
    required_proof: tuple[str, ...]


RELEASE_MATRIX: tuple[EvidenceRequirement, ...] = (
    EvidenceRequirement("core.less_is_more", "Feishu-only service boundary", ("text_reply", "duplicate_text", "ws_sdk_envelope_normalization"), ("text_message_reply", "duplicate_callback"), ("gateway_job", "duplicate_guard", "ws_sdk_envelope")),
    EvidenceRequirement("core.borrow_what_works", "Memory/evolution mechanisms improve workflows", ("memory_supersession", "memory_durability_policy", "temporal_state_recovery", "trace2skill_promotion"), ("memory_supersession", "trace2skill_promotion"), ("memory_supersession", "memory_durability", "temporal_state_recovery", "trace2skill_regression")),
    EvidenceRequirement("core.deepseek_adapted", "DeepSeek usage and degradation are measured", ("deepseek_usage", "partial_failure"), ("deepseek_usage", "partial_failure"), ("model_usage", "partial_failure")),
    EvidenceRequirement("trait.curiosity", "Reflection stores durable facts only", ("memory_supersession", "memory_durability_policy", "temporal_state_recovery"), ("memory_supersession",), ("memory_supersession", "memory_durability", "temporal_state_recovery")),
    EvidenceRequirement("trait.reliability", "Evidence-backed runtime delivery", ("text_reply", "image_understanding", "ack_boundary", "ws_sdk_envelope_normalization", "card_fallback", "duplicate_text"), ("text_message_reply", "image_message_reply", "ws_ack_boundary", "card_fallback", "duplicate_callback"), ("gateway_job", "image_understanding", "ack_boundary", "ws_sdk_envelope", "card_fallback", "duplicate_guard")),
    EvidenceRequirement("trait.fact_hygiene", "Facts and shared evidence are source-bound and redacted", ("memory_supersession", "fact_hygiene_policy", "partial_failure"), ("memory_supersession", "partial_failure"), ("memory_supersession", "source_required", "partial_failure")),
    EvidenceRequirement("trait.multidisciplinary", "Research mechanisms prove product value", ("image_understanding", "long_conversation", "trace2skill_promotion"), ("image_understanding", "long_conversation", "trace2skill_promotion"), ("image_understanding", "long_context", "trace2skill_regression")),
    EvidenceRequirement("trait.negative_capability", "Failures are explicit to users and operators", ("partial_failure",), ("partial_failure",), ("partial_failure",)),
    EvidenceRequirement("trait.low_ego_high_drive", "Claims require replayable evidence and transferable state", ("state_handoff", "release_gate"), ("verified_ws_bundle",), ("state_handoff", "release_gate")),
)

HARNESS_LAYER_MATRIX: tuple[HarnessLayerRequirement, ...] = (
    HarnessLayerRequirement("Execution", "Feishu events execute through ACK, SDK envelope normalization, bounded workers, durable jobs, quotas, and delivery.", ("gateway_job", "ack_boundary", "ws_sdk_envelope", "worker_saturation", "workspace_boundary", "resource_quota", "duplicate_guard", "card_fallback", "partial_failure")),
    HarnessLayerRequirement("Tooling", "Tool use is governed by confirmation, delegated workers, and failure boundaries.", ("card_fallback", "delegated_worker_trace", "partial_failure", "state_handoff")),
    HarnessLayerRequirement("Context", "Long context and memory are retained, masked, superseded, recovered, and source-bound.", ("long_context", "memory_supersession", "memory_durability", "temporal_state_recovery", "source_required")),
    HarnessLayerRequirement("Lifecycle", "Failures become replay-validated skills, delegated work traces, and release state transfers.", ("trace2skill_regression", "delegated_worker_trace", "state_handoff", "release_gate")),
    HarnessLayerRequirement("Observability", "Runtime, model, failure, pressure, and handoff claims carry operator evidence.", ("gateway_job", "model_usage", "worker_saturation", "trace_failure_diagnosis", "partial_failure", "state_handoff")),
    HarnessLayerRequirement("Verification", "Local harness claims are matrixed, envelope-backed, release-gated, SDK-envelope guarded, and ablation-guarded.", ("release_gate", "trace2skill_regression", "trace_failure_diagnosis", "ws_sdk_envelope", "model_usage", "adaptive_simplification")),
    HarnessLayerRequirement("Governance", "Evidence, facts, secrets, runtime stores, workspaces, confirmations, and resource use remain bounded.", ("source_required", "memory_durability", "temporal_state_recovery", "runtime_lock", "workspace_boundary", "resource_quota", "partial_failure", "state_handoff")),
)


def evaluate_release_matrix(results: list[dict[str, Any]]) -> dict[str, Any]:
    proof_by_name = _proof_status_map(results)
    return _evaluate_release_matrix_from_proof_status(proof_by_name)


def evaluate_proof_ablation(
    results: list[dict[str, Any]],
    *,
    target_proof: str,
    ignore_proofs: tuple[str, ...] = ("adaptive_simplification",),
) -> dict[str, Any]:
    """Return the matrix delta when a load-bearing proof is removed."""

    proof_by_name = _proof_status_map(results)
    baseline = _evaluate_release_matrix_from_proof_status(proof_by_name, ignore_proofs=ignore_proofs)
    target_scenarios = sorted(
        name
        for name, proof in proof_by_name.items()
        if target_proof in proof.get("proof", [])
    )
    ablated_proof_by_name = {
        name: {
            **proof,
            "proof": [proof_id for proof_id in proof.get("proof", []) if proof_id != target_proof],
            "missing": [*proof.get("missing", []), f"ablated:{target_proof}"],
        }
        for name, proof in proof_by_name.items()
    }
    scenario_ablated_by_name = {
        name: {
            **proof,
            "passed": False if name in target_scenarios else proof.get("passed"),
            "proof": [proof_id for proof_id in proof.get("proof", []) if proof_id != target_proof],
            "missing": [*proof.get("missing", []), f"ablated:{target_proof}"] if name in target_scenarios else proof.get("missing", []),
        }
        for name, proof in proof_by_name.items()
    }
    proof_ablated = _evaluate_release_matrix_from_proof_status(ablated_proof_by_name, ignore_proofs=ignore_proofs)
    scenario_ablated = _evaluate_release_matrix_from_proof_status(scenario_ablated_by_name, ignore_proofs=ignore_proofs)
    affected_layers = [
        row["layer"]
        for row in proof_ablated["harness_layers"]["rows"]
        if target_proof in row.get("missing_proof", [])
    ]
    affected_rows = [
        row["id"]
        for row in scenario_ablated["rows"]
        if any(name in row.get("missing_proof", []) for name in target_scenarios)
    ]
    return {
        "schema": "yinyo.proof_ablation.v1",
        "target_proof": target_proof,
        "target_scenarios": target_scenarios,
        "baseline_ok": baseline["ok"],
        "proof_ablated_ok": proof_ablated["ok"],
        "scenario_ablated_ok": scenario_ablated["ok"],
        "ablated_ok": proof_ablated["ok"] and scenario_ablated["ok"],
        "affected_layers": affected_layers,
        "affected_rows": affected_rows,
        "missing_proof_detected": bool(affected_layers or affected_rows),
        "ignored_self_proofs": list(ignore_proofs),
    }


def _proof_status_map(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        item.get("name"): _proof_status(item)
        for item in results
        if isinstance(item.get("name"), str)
    }


def _evaluate_release_matrix_from_proof_status(
    proof_by_name: dict[str, dict[str, Any]],
    *,
    ignore_proofs: tuple[str, ...] = (),
) -> dict[str, Any]:
    ignored = set(ignore_proofs)
    proof_by_name = {
        name: {
            **proof,
            "proof": [proof_id for proof_id in proof.get("proof", []) if proof_id not in ignored],
        }
        for name, proof in proof_by_name.items()
    }
    passed = {
        name
        for name, proof in proof_by_name.items()
        if proof["passed"] is True
    }
    rows = []
    for requirement in RELEASE_MATRIX:
        missing = [
            name
            for name in requirement.required_scenarios
            if name not in passed
        ]
        missing_proof = [
            name
            for name in requirement.required_scenarios
            if name not in proof_by_name or proof_by_name[name]["passed"] is not True
        ]
        row_proofs = sorted({
            proof_id
            for name in requirement.required_scenarios
            for proof_id in proof_by_name.get(name, {}).get("proof", [])
        })
        missing_required_proof = [
            proof_id
            for proof_id in requirement.required_proof
            if proof_id not in row_proofs
        ]
        rows.append({
            "id": requirement.id,
            "claim": requirement.claim,
            "required_scenarios": list(requirement.required_scenarios),
            "local_harness_required": list(requirement.required_scenarios),
            "live_product_required": list(requirement.live_required),
            "required_proof": list(requirement.required_proof),
            "provided_proof": row_proofs,
            "missing": missing,
            "missing_proof": missing_proof + missing_required_proof,
            "missing_required_proof": missing_required_proof,
            "local_harness_passed": not missing_proof and not missing_required_proof,
            "live_product_status": "required_for_1_0",
            "passed": not missing_proof and not missing_required_proof,
        })
    harness_layers = _evaluate_harness_layers(proof_by_name, ignore_proofs=ignore_proofs)
    return {
        "ok": all(row["passed"] for row in rows) and harness_layers["ok"],
        "rows": rows,
        "harness_layers": harness_layers,
        "passed_scenarios": sorted(passed),
        "proof_status": proof_by_name,
        "scope": "local_harness_evidence",
        "live_product_required_for_1_0": True,
    }


def evaluate_live_release_matrix(
    *,
    smoke_chain: dict[str, Any] | None = None,
    advanced_live: dict[str, Any] | None = None,
    bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate 1.0 live evidence against the same product rows as the local matrix."""

    live_passed = _live_passed_scenarios(smoke_chain=smoke_chain, advanced_live=advanced_live, bundle=bundle)
    rows = []
    for requirement in RELEASE_MATRIX:
        missing = [name for name in requirement.live_required if name not in live_passed]
        rows.append({
            "id": requirement.id,
            "claim": requirement.claim,
            "live_product_required": list(requirement.live_required),
            "live_passed": [name for name in requirement.live_required if name in live_passed],
            "live_missing": missing,
            "passed": not missing,
        })
    return {
        "schema": "yinyo.live_release_matrix.v1",
        "ok": all(row["passed"] for row in rows),
        "rows": rows,
        "passed_scenarios": sorted(live_passed),
        "missing_scenarios": sorted({name for row in rows for name in row["live_missing"]}),
        "bundle_verified": bool(bundle and bundle.get("ok")),
    }


def _live_passed_scenarios(
    *,
    smoke_chain: dict[str, Any] | None,
    advanced_live: dict[str, Any] | None,
    bundle: dict[str, Any] | None,
) -> set[str]:
    if bundle and bundle.get("ok") is True:
        passed = {"verified_ws_bundle"}
        manifest = bundle.get("manifest", {}) if isinstance(bundle.get("manifest"), dict) else {}
        chain = manifest.get("chain", {}) if isinstance(manifest.get("chain"), dict) else {}
        advanced = manifest.get("advanced", {}) if isinstance(manifest.get("advanced"), dict) else {}
        advanced_attestation = manifest.get("advanced_ref_attestation", {}) if isinstance(manifest.get("advanced_ref_attestation"), dict) else {}
        top_level_correlation = manifest.get("correlation", {}) if isinstance(manifest.get("correlation"), dict) else {}
    else:
        passed = set()
        chain = smoke_chain or {}
        advanced = advanced_live or {}
        advanced_attestation = {}
        top_level_correlation = {}
    smoke = chain.get("smoke", {}) if isinstance(chain.get("smoke"), dict) else {}
    for scenario in smoke.get("passed", []) if isinstance(smoke.get("passed", []), list) else []:
        passed.add(str(scenario))
    correlation = chain.get("correlation", {}) if isinstance(chain.get("correlation"), dict) else top_level_correlation
    correlation_chains = correlation.get("chains", []) if isinstance(correlation.get("chains", []), list) else []
    if any(
        isinstance(item, dict)
        and item.get("ok") is True
        and item.get("scenario") in {"text_message_reply", "image_message_reply", "card_fallback", "duplicate_callback"}
        for item in correlation_chains
    ):
        passed.add("ws_ack_boundary")
    for scenario in advanced.get("passed", []) if isinstance(advanced.get("passed", []), list) else []:
        scenario_id = str(scenario)
        if bundle and bundle.get("ok") is True and not _advanced_scenario_attested(advanced_attestation, scenario_id):
            continue
        passed.add(scenario_id)
    return passed


def _advanced_scenario_attested(attestation: dict[str, Any], scenario: str) -> bool:
    if not isinstance(attestation, dict) or attestation.get("schema") != "yinyo.advanced_ref_attestation.v1":
        return False
    if attestation.get("ok") is not True:
        return False
    scenarios = attestation.get("scenarios", {})
    item = scenarios.get(scenario, {}) if isinstance(scenarios, dict) else {}
    if not isinstance(item, dict):
        return False
    return (
        item.get("schema") == "yinyo.advanced_ref_attestation.scenario.v1"
        and item.get("scenario") == scenario
        and item.get("ok") is True
        and item.get("ref_resolution_schema") == "yinyo.advanced_ref_resolution.v1"
        and item.get("proof_schema") == "yinyo.advanced_live_proof.v1"
        and bool(item.get("proof_digest"))
        and item.get("ref_resolution_mode") != "skipped_for_redacted_bundle"
        and not item.get("unresolved")
    )


def _evaluate_harness_layers(
    proof_by_name: dict[str, dict[str, Any]],
    *,
    ignore_proofs: tuple[str, ...] = (),
) -> dict[str, Any]:
    ignored = set(ignore_proofs)
    passed_proofs = {
        proof_id
        for proof in proof_by_name.values()
        if proof.get("passed") is True
        for proof_id in proof.get("proof", [])
        if proof_id not in ignored
    }
    rows = []
    for requirement in HARNESS_LAYER_MATRIX:
        required = [proof_id for proof_id in requirement.required_proof if proof_id not in ignored]
        missing = [proof_id for proof_id in required if proof_id not in passed_proofs]
        rows.append({
            "layer": requirement.layer,
            "claim": requirement.claim,
            "required_proof": required,
            "missing_proof": missing,
            "passed": not missing,
        })
    return {
        "schema": "yinyo.harness_layers.v1",
        "framework": "ETCLOVG",
        "source": "https://picrew.github.io/LLM-Harness/",
        "rows": rows,
        "passed_layers": [row["layer"] for row in rows if row["passed"]],
        "missing_layers": [row["layer"] for row in rows if not row["passed"]],
        "ok": all(row["passed"] for row in rows),
    }


def _proof_status(item: dict[str, Any]) -> dict[str, Any]:
    name = item.get("name", "")
    checks = SCENARIO_PROOF_CHECKS.get(name, ())
    envelope_missing = _proof_envelope_missing(item)
    failed = [
        proof_id
        for proof_id, predicate in checks
        if not predicate(item)
    ]
    return {
        "passed": item.get("passed") is True and not envelope_missing and not failed and bool(checks),
        "proof": [proof_id for proof_id, _ in checks],
        "missing": envelope_missing + failed,
    }


def _proof_envelope_missing(item: dict[str, Any]) -> list[str]:
    envelope = item.get("proof_envelope", {})
    if not isinstance(envelope, dict):
        return ["proof_envelope"]
    missing: list[str] = []
    if envelope.get("schema") != "yinyo.proof_envelope.v1":
        missing.append("proof_envelope.schema")
    if envelope.get("source") in (None, "", "fixture_only"):
        missing.append("proof_envelope.source")
    refs = envelope.get("refs", {})
    if not isinstance(refs, dict) or not refs:
        missing.append("proof_envelope.refs")
    missing.extend(_proof_contract_missing(item, envelope, refs if isinstance(refs, dict) else {}))
    digest = envelope.get("digest")
    expected = _proof_envelope_digest(item)
    if not isinstance(digest, str) or len(digest) != 64:
        missing.append("proof_envelope.digest")
    elif digest != expected:
        missing.append("proof_envelope.digest_mismatch")
    return missing


def _proof_contract_missing(item: dict[str, Any], envelope: dict[str, Any], refs: dict[str, Any]) -> list[str]:
    if not item.get("corpus_id"):
        return []
    contract = item.get("proof_contract", {})
    missing: list[str] = []
    if not isinstance(contract, dict):
        return ["proof_contract"]
    if contract.get("schema") != "yinyo.proof_contract.v1":
        missing.append("proof_contract.schema")
    if contract.get("corpus_id") != item.get("corpus_id"):
        missing.append("proof_contract.corpus_id")
    if contract.get("corpus_version") != item.get("corpus_version"):
        missing.append("proof_contract.corpus_version")
    if contract.get("source") and envelope.get("source") != contract.get("source"):
        missing.append("proof_contract.source")
    required = contract.get("refs_required", [])
    if not isinstance(required, list):
        missing.append("proof_contract.refs_required")
        required = []
    for ref in required:
        if not isinstance(ref, str) or not ref:
            missing.append("proof_contract.refs_required")
            continue
        if ref not in refs or refs.get(ref) in (None, "", [], {}):
            missing.append(f"proof_envelope.refs_required:{ref}")
    return missing


def _proof_envelope_digest(item: dict[str, Any]) -> str:
    canonical = {
        key: value
        for key, value in item.items()
        if key != "proof_envelope"
    }
    payload = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _evidence(item: dict[str, Any]) -> dict[str, Any]:
    evidence = item.get("evidence", {})
    return evidence if isinstance(evidence, dict) else {}


def _gateway(item: dict[str, Any]) -> dict[str, Any]:
    gateway = item.get("gateway", {})
    return gateway if isinstance(gateway, dict) else {}


def _run(item: dict[str, Any]) -> dict[str, Any]:
    run = item.get("run", {})
    return run if isinstance(run, dict) else {}


def _bundle(item: dict[str, Any]) -> dict[str, Any]:
    bundle = item.get("bundle", {})
    return bundle if isinstance(bundle, dict) else {}


def _text_reply_proves_gateway_job(item: dict[str, Any]) -> bool:
    gateway = _gateway(item)
    return (
        item.get("status_code") == 200
        and item.get("job") is True
        and item.get("job_status") == "succeeded"
        and item.get("delivery") is True
        and gateway.get("job_status") == "succeeded"
        and gateway.get("delivery") is True
        and bool(gateway.get("message_ids"))
        and _run(item).get("correlation_id") == gateway.get("event_key")
    )


def _duplicate_proves_guard(item: dict[str, Any]) -> bool:
    gateway = _gateway(item)
    return (
        item.get("duplicate") is True
        and item.get("job") is False
        and item.get("delivery") is False
        and gateway.get("duplicate") is True
        and gateway.get("job_id", "") == ""
        and gateway.get("delivery") is False
    )


def _image_understanding_proof(item: dict[str, Any]) -> bool:
    evidence = _evidence(item)
    gateway = _gateway(item)
    return (
        evidence.get("agent_text_contains_description") is True
        and evidence.get("job_status") == "succeeded"
        and evidence.get("delivery") is True
        and gateway.get("job_status") == "succeeded"
        and gateway.get("delivery") is True
    )


def _long_context_proof(item: dict[str, Any]) -> bool:
    evidence = _evidence(item)
    return (
        evidence.get("estimated_tokens_before", 0) > 0
        and evidence.get("masked_observations_after", 0) > 0
        and evidence.get("protected_recent_context") is True
    )


def _memory_supersession_proof(item: dict[str, Any]) -> bool:
    evidence = _evidence(item)
    return (
        evidence.get("old_fact_status") == "superseded"
        and evidence.get("new_fact_version", 0) >= 2
        and evidence.get("audit_trail_length") == 2
        and len(evidence.get("search_result_ids", [])) >= 1
    )


def _memory_durability_proof(item: dict[str, Any]) -> bool:
    evidence = _evidence(item)
    return (
        evidence.get("stored") == 1
        and evidence.get("rejected") == 1
        and "ephemeral_content" in evidence.get("reasons", [])
        and evidence.get("active_categories") == ["Preferences"]
    )


def _temporal_state_recovery_proof(item: dict[str, Any]) -> bool:
    evidence = _evidence(item)
    return (
        evidence.get("state_report_schema") == "yinyo.temporal_state_report.v1"
        and evidence.get("recovered_from_disk") is True
        and evidence.get("provenance_complete") is True
        and evidence.get("missing_provenance") == []
        and evidence.get("superseded") == 1
        and evidence.get("archived") == 1
        and evidence.get("stale") == 0
        and evidence.get("audit_trail_length") == 2
        and evidence.get("search_excludes_old") is True
        and len(evidence.get("search_result_ids", [])) >= 1
    )


def _source_required_proof(item: dict[str, Any]) -> bool:
    evidence = _evidence(item)
    return (
        evidence.get("status") == "source_required"
        and evidence.get("source_required") is True
        and evidence.get("source_satisfied") is False
    )


def _trace2skill_proof(item: dict[str, Any]) -> bool:
    evidence = _evidence(item)
    return (
        evidence.get("regression_fixture") is True
        and evidence.get("regression_replay_passed") is True
        and evidence.get("validation_passed") is True
        and evidence.get("replay_command_passed") is True
        and evidence.get("pre_skill_failure_reproduced") is True
        and evidence.get("post_skill_guardrail_applied") is True
        and evidence.get("guardrail_applied") is True
        and evidence.get("pre_skill_failed") is True
        and evidence.get("post_skill_passed") is True
        and bool(evidence.get("pre_skill_run_ref"))
        and bool(evidence.get("post_skill_run_ref"))
        and evidence.get("pre_skill_run_ref") != evidence.get("post_skill_run_ref")
        and evidence.get("replay_exit_code") == 0
        and evidence.get("replay_stdout_mentions_failure") is True
        and evidence.get("replay_stdout_mentions_guardrail") is True
        and evidence.get("promotion_record") is True
        and evidence.get("promotion_status") in {"proven", "stable"}
        and bool(evidence.get("failure_trace_ref"))
        and bool(evidence.get("post_promotion_run_ref"))
    )


def _ack_boundary_proof(item: dict[str, Any]) -> bool:
    evidence = _evidence(item)
    gateway = _gateway(item)
    envelope = item.get("proof_envelope", {})
    refs = envelope.get("refs", {}) if isinstance(envelope, dict) else {}
    ack_latency_ms = evidence.get("ack_latency_ms")
    ack_deadline_ms = evidence.get("ack_deadline_ms")
    return (
        item.get("status_code") == 200
        and item.get("job") is True
        and evidence.get("schema") == "yinyo.ack_boundary.v1"
        and evidence.get("async_dispatch_requested") is True
        and evidence.get("ack_before_agent_execution") is True
        and evidence.get("post_ack_handler_executed") is True
        and evidence.get("post_ack_delivery") is True
        and isinstance(ack_latency_ms, (int, float))
        and isinstance(ack_deadline_ms, (int, float))
        and ack_latency_ms >= 0
        and ack_deadline_ms > 0
        and ack_latency_ms <= ack_deadline_ms
        and refs.get("ack_latency_ms") == ack_latency_ms
        and refs.get("ack_deadline_ms") == ack_deadline_ms
        and refs.get("job_id") == gateway.get("job_id")
        and refs.get("case") == item.get("corpus_id")
        and gateway.get("async_dispatch") is True
        and gateway.get("job_status_at_ack") == "queued"
        and gateway.get("post_ack_job_status") == "succeeded"
    )


def _ws_sdk_envelope_proof(item: dict[str, Any]) -> bool:
    evidence = _evidence(item)
    gateway = _gateway(item)
    envelope = item.get("proof_envelope", {})
    refs = envelope.get("refs", {}) if isinstance(envelope, dict) else {}
    ack_latency_ms = evidence.get("ack_latency_ms")
    ack_deadline_ms = evidence.get("ack_deadline_ms")
    event_key = evidence.get("normalized_uuid")
    return (
        item.get("status_code") == 200
        and item.get("job") is True
        and evidence.get("schema") == "yinyo.ws_sdk_envelope_normalization.v1"
        and evidence.get("sdk_schema") == "2.0"
        and evidence.get("header_event_id") == event_key
        and evidence.get("normalized_type") == "event_callback"
        and evidence.get("normalized_message_type") == "text"
        and evidence.get("normalized_text") == "hello from sdk"
        and evidence.get("gateway_received_normalized") is True
        and evidence.get("async_dispatch_requested") is True
        and evidence.get("logger_recorded_ws_event") is True
        and isinstance(ack_latency_ms, (int, float))
        and isinstance(ack_deadline_ms, (int, float))
        and ack_latency_ms >= 0
        and ack_deadline_ms > 0
        and ack_latency_ms <= ack_deadline_ms
        and gateway.get("event_key") == event_key
        and gateway.get("async_dispatch") is True
        and gateway.get("job_status_at_ack") == "queued"
        and refs.get("case") == item.get("corpus_id")
        and refs.get("sdk_event_id") == event_key
        and refs.get("normalized_uuid") == event_key
        and refs.get("job_id") == gateway.get("job_id")
    )


def _worker_saturation_proof(item: dict[str, Any]) -> bool:
    evidence = _evidence(item)
    return (
        evidence.get("schema") == "yinyo.worker_saturation.v1"
        and evidence.get("max_workers") == 1
        and evidence.get("queued_jobs", 0) >= 2
        and evidence.get("rejected_jobs", 0) >= 1
        and evidence.get("rejection_error") == "job queue saturated"
        and evidence.get("rejection_recorded") is True
        and "rejected" in evidence.get("statuses", [])
        and bool(evidence.get("job_store"))
    )


def _runtime_lock_proof(item: dict[str, Any]) -> bool:
    evidence = _evidence(item)
    return (
        evidence.get("schema") == "yinyo.runtime_lock_single_writer.v1"
        and evidence.get("second_writer_blocked") is True
        and evidence.get("second_error_mentions_owner") is True
        and evidence.get("available_while_locked") is False
        and evidence.get("available_after_release") is True
        and bool(evidence.get("lock_path"))
        and bool(evidence.get("owner"))
    )


def _workspace_boundary_proof(item: dict[str, Any]) -> bool:
    evidence = _evidence(item)
    errors = evidence.get("blocked_errors", {}) if isinstance(evidence.get("blocked_errors"), dict) else {}
    return (
        evidence.get("schema") == "yinyo.workspace_boundary.v1"
        and evidence.get("inside_read_ok") is True
        and evidence.get("blocked_operations") == 5
        and evidence.get("escaped_file_created") is False
        and {"absolute_read", "traversal_read", "traversal_search", "traversal_write", "traversal_run_workdir"}.issubset(set(errors))
    )


def _resource_quota_proof(item: dict[str, Any]) -> bool:
    evidence = _evidence(item)
    return (
        evidence.get("schema") == "yinyo.resource_quota.v1"
        and evidence.get("read_limit", 0) > 0
        and evidence.get("read_shown") == evidence.get("read_limit")
        and evidence.get("read_total_lines", 0) > evidence.get("read_limit", 0)
        and evidence.get("search_result_cap") == 50
        and evidence.get("search_count") == 50
        and evidence.get("search_returned") == 50
        and evidence.get("large_file_skipped") is True
        and evidence.get("stdout_chars", 999999) <= evidence.get("stdout_limit", 0)
        and evidence.get("stderr_chars", 999999) <= evidence.get("stderr_limit", 0)
        and evidence.get("timeout_blocked") is True
        and evidence.get("timeout_exit_code") == -1
    )


def _model_usage_proof(item: dict[str, Any]) -> bool:
    evidence = _evidence(item)
    usage = evidence.get("model_usage", {})
    envelope = evidence.get("model_envelope", {})
    budget = envelope.get("budget", {}) if isinstance(envelope, dict) else {}
    retry_attempts = envelope.get("retry_attempts", []) if isinstance(envelope, dict) else []
    fallback_attempts = envelope.get("fallback_attempts", []) if isinstance(envelope, dict) else []
    error_attempts = envelope.get("error_attempts", []) if isinstance(envelope, dict) else []
    error_classes = set(envelope.get("error_classifications", [])) if isinstance(envelope, dict) else set()
    return (
        isinstance(usage, dict)
        and usage.get("prompt_tokens", 0) > 0
        and usage.get("completion_tokens", 0) > 0
        and usage.get("total_tokens") == usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
        and usage.get("estimated_cost_usd", 0) > 0
        and evidence.get("manifest_matches_result") is True
        and str(evidence.get("default_model", "")).startswith("deepseek")
        and isinstance(envelope, dict)
        and envelope.get("schema") == "yinyo.model_envelope.v1"
        and envelope.get("within_budget") is True
        and budget.get("max_total_tokens", 0) >= usage.get("total_tokens", 0)
        and budget.get("max_estimated_cost_usd", 0) >= usage.get("estimated_cost_usd", 0)
        and len(retry_attempts) >= 2
        and any(item.get("ok") is False and item.get("error") == "timeout" for item in retry_attempts if isinstance(item, dict))
        and any(item.get("ok") is True for item in retry_attempts if isinstance(item, dict))
        and envelope.get("retry_recovered") is True
        and len(fallback_attempts) >= 2
        and envelope.get("fallback_observed") is True
        and str(envelope.get("fallback_from", "")).startswith("deepseek")
        and len(error_attempts) >= 2
        and {"timeout", "rate_limit"}.issubset(error_classes)
        and envelope.get("degradation_status") == "model_error"
        and bool(envelope.get("user_visible_degradation"))
    )


def _card_fallback_proof(item: dict[str, Any]) -> bool:
    evidence = _evidence(item)
    gateway = _gateway(item)
    smoke_passed = set(evidence.get("smoke_passed", []))
    return (
        evidence.get("gateway_fallback") is True
        and evidence.get("card_invalid_error_detected") is True
        and {"text_message_reply", "card_fallback"}.issubset(smoke_passed)
        and gateway.get("fallback") is True
    )


def _partial_failure_proof(item: dict[str, Any]) -> bool:
    evidence = _evidence(item)
    return (
        evidence.get("user_visible_status") == "partial"
        and evidence.get("blocked_evidence_records", 0) > 0
        and evidence.get("no_false_success") is True
        and bool(evidence.get("operator_evidence_file"))
    )


def _trace_failure_diagnosis_proof(item: dict[str, Any]) -> bool:
    evidence = _evidence(item)
    layers = set(evidence.get("evidence_ref_layers", []))
    return (
        evidence.get("diagnosis_schema") == "yinyo.trace_failure_diagnosis.v1"
        and evidence.get("root_cause") == "runtime_job_failed"
        and evidence.get("trace_complete") is True
        and "job_store" in layers
        and evidence.get("suggested_action_present") is True
        and evidence.get("candidate_count", 0) >= 1
    )


def _adaptive_simplification_proof(item: dict[str, Any]) -> bool:
    evidence = _evidence(item)
    affected_layers = set(evidence.get("affected_layers", []))
    affected_rows = set(evidence.get("affected_rows", []))
    return (
        evidence.get("ablation_schema") == "yinyo.proof_ablation.v1"
        and evidence.get("target_proof") == "model_usage"
        and evidence.get("baseline_ok") is True
        and evidence.get("proof_ablated_ok") is False
        and evidence.get("scenario_ablated_ok") is False
        and evidence.get("missing_proof_detected") is True
        and {"Observability", "Verification"}.issubset(affected_layers)
        and "core.deepseek_adapted" in affected_rows
    )


def _release_gate_proof(item: dict[str, Any]) -> bool:
    evidence = _evidence(item)
    required = set(evidence.get("required_live_scenarios", []))
    missing = set(evidence.get("missing_live_scenarios", []))
    bundle = _bundle(item)
    return (
        evidence.get("transport") == "ws"
        and evidence.get("live_smoke_blocks_1_0_until_present") is True
        and {"text_message_reply", "image_message_reply", "card_fallback", "duplicate_callback"}.issubset(required)
        and required.issubset(missing)
        and "url_verification" not in required
        and bundle.get("required") is True
        and bundle.get("verified") is False
    )


def _state_handoff_proof(item: dict[str, Any]) -> bool:
    evidence = _evidence(item)
    return (
        evidence.get("schema") == "yinyo.handoff.v1"
        and evidence.get("correlation_id") == "scenario-handoff"
        and evidence.get("intent_recorded") is True
        and evidence.get("permissions_recorded") is True
        and evidence.get("source_audit_recorded") is True
        and evidence.get("budget_recorded") is True
        and evidence.get("trace_history_recorded") is True
        and evidence.get("manifest_linked") is True
        and evidence.get("resume_schema") == "yinyo.handoff_resume.v1"
        and evidence.get("resume_ready") is True
        and evidence.get("resume_ok") is True
        and evidence.get("resume_artifacts_exist") is True
        and evidence.get("resume_budget_recoverable") is True
        and evidence.get("resume_trace_recoverable") is True
        and evidence.get("resume_inherits_intent") is True
        and evidence.get("resume_inherits_constraints") is True
        and evidence.get("resume_inherits_permissions") is True
        and evidence.get("resume_inherits_artifacts") is True
        and evidence.get("resume_inherits_provenance") is True
        and evidence.get("resume_inherits_budget") is True
        and evidence.get("resume_inherits_trace_history") is True
        and evidence.get("resume_inherits_risk") is True
        and evidence.get("resume_inherits_unresolved") is True
    )


def _delegated_worker_trace_proof(item: dict[str, Any]) -> bool:
    evidence = _evidence(item)
    envelope = item.get("proof_envelope", {})
    refs = envelope.get("refs", {}) if isinstance(envelope, dict) else {}
    tool_names = evidence.get("tool_names", [])
    trace_refs = evidence.get("trace_refs", [])
    return (
        evidence.get("schema") == "yinyo.delegated_worker_trace.v1"
        and evidence.get("parent_context_shared") is True
        and evidence.get("worker_status") == "success"
        and isinstance(evidence.get("parent_run_id"), str)
        and evidence.get("parent_run_id")
        and isinstance(evidence.get("worker_run_id"), str)
        and evidence.get("worker_run_id", "").startswith("sub-")
        and evidence.get("worker_run_id") != evidence.get("parent_run_id")
        and evidence.get("tool_traces_count", 0) >= 1
        and "do_search" in tool_names
        and isinstance(trace_refs, list)
        and trace_refs
        and all(isinstance(ref, dict) and ref.get("tool") for ref in trace_refs)
        and refs.get("case") == item.get("corpus_id")
        and refs.get("parent_run_id") == evidence.get("parent_run_id")
        and refs.get("worker_run_id") == evidence.get("worker_run_id")
        and refs.get("tool_traces_count") == evidence.get("tool_traces_count")
    )


SCENARIO_PROOF_CHECKS: dict[str, tuple[tuple[str, Any], ...]] = {
    "text_reply": (("gateway_job", _text_reply_proves_gateway_job),),
    "duplicate_text": (("duplicate_guard", _duplicate_proves_guard),),
    "image_understanding": (("image_understanding", _image_understanding_proof),),
    "long_conversation": (("long_context", _long_context_proof),),
    "memory_supersession": (("memory_supersession", _memory_supersession_proof),),
    "memory_durability_policy": (("memory_durability", _memory_durability_proof),),
    "temporal_state_recovery": (("temporal_state_recovery", _temporal_state_recovery_proof),),
    "fact_hygiene_policy": (("source_required", _source_required_proof),),
    "trace2skill_promotion": (("trace2skill_regression", _trace2skill_proof),),
    "ack_boundary": (("ack_boundary", _ack_boundary_proof),),
    "ws_sdk_envelope_normalization": (("ws_sdk_envelope", _ws_sdk_envelope_proof),),
    "worker_saturation_backpressure": (("worker_saturation", _worker_saturation_proof),),
    "runtime_lock_single_writer": (("runtime_lock", _runtime_lock_proof),),
    "workspace_boundary": (("workspace_boundary", _workspace_boundary_proof),),
    "resource_quota": (("resource_quota", _resource_quota_proof),),
    "trace_failure_diagnosis": (("trace_failure_diagnosis", _trace_failure_diagnosis_proof),),
    "adaptive_simplification": (("adaptive_simplification", _adaptive_simplification_proof),),
    "deepseek_usage": (("model_usage", _model_usage_proof),),
    "card_fallback": (("card_fallback", _card_fallback_proof),),
    "partial_failure": (("partial_failure", _partial_failure_proof),),
    "state_handoff": (("state_handoff", _state_handoff_proof),),
    "delegated_worker_trace": (("delegated_worker_trace", _delegated_worker_trace_proof),),
    "release_gate": (("release_gate", _release_gate_proof),),
}
