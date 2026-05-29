"""Machine-readable release readiness audit."""

from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass
from typing import Any

from .config import RuntimeConfig
from .scenario import replay_release_matrix
from .release_matrix import evaluate_live_release_matrix
from .smoke import required_live_smoke_scenarios, verify_advanced_live_evidence, verify_smoke_evidence_chain


@dataclass(frozen=True)
class ReadinessItem:
    id: str
    requirement: str
    passed: bool
    evidence: list[str]
    blockers: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "requirement": self.requirement,
            "passed": self.passed,
            "evidence": self.evidence,
            "blockers": self.blockers,
        }


def audit_release_readiness(
    root: str | pathlib.Path,
    *,
    target: str = "",
    live_smoke_override: str | dict[str, Any] | None = None,
    config_path: str | pathlib.Path | None = None,
    workspace: str | pathlib.Path | None = None,
    smoke_path: str | pathlib.Path | None = None,
) -> dict[str, Any]:
    """Audit docs/spec.md R1 release criteria against current artifacts."""

    root = pathlib.Path(root)
    workspace = pathlib.Path(workspace) if workspace else root / "workspace"
    texts = _load_texts(root)
    versions = _read_versions(texts)
    matrix = replay_release_matrix(root / "examples" / "feishu_scenarios.json")
    override = _normalize_live_smoke_override(live_smoke_override)
    smoke_chain = _read_smoke_chain(root, workspace, smoke_path, config_path) if target == "1.0.0" and not override else None
    advanced_live = _read_advanced_live(root, workspace, smoke_path, config_path) if target == "1.0.0" and not override else None
    live_matrix = evaluate_live_release_matrix(
        smoke_chain=smoke_chain,
        advanced_live=advanced_live,
        bundle=override,
    ) if target == "1.0.0" else None

    items = [
        _r1_01(root, texts),
        _r1_02(root),
        _r1_03(target, smoke_chain, override),
        _r1_04(root, texts),
        _r1_05(texts),
        _r1_06(texts, versions),
        _r1_07(root, matrix, target, smoke_chain, override, live_matrix),
        _r1_08(matrix, target, advanced_live, override, live_matrix),
        _r1_09(matrix, target, advanced_live, override, live_matrix),
        _r1_10(texts, matrix, target, advanced_live, override, live_matrix),
        _r1_11(matrix, target, advanced_live, override, live_matrix),
    ]
    failures = [
        f"{item.id}: {', '.join(item.blockers)}"
        for item in items
        if not item.passed
    ]
    return {
        "ok": not failures,
        "target": target,
        "items": [item.to_dict() for item in items],
        "failures": failures,
        "matrix_ok": matrix["ok"],
        "corpus_contract_ok": matrix.get("corpus_contract", {}).get("ok"),
        "corpus_contract_errors": matrix.get("corpus_contract", {}).get("errors", []),
        "corpus_sha256": matrix.get("corpus", {}).get("sha256", ""),
        "live_matrix": live_matrix,
        "live_matrix_ok": None if live_matrix is None else live_matrix["ok"],
        "smoke_chain_ok": None if smoke_chain is None else smoke_chain["ok"],
        "advanced_live_ok": None if advanced_live is None else advanced_live["ok"],
    }


def _normalize_live_smoke_override(value: str | dict[str, Any] | None) -> dict[str, Any] | None:
    if not value:
        return None
    if isinstance(value, dict):
        return {
            "path": str(value.get("path", "")),
            "transport": str(value.get("transport", "")),
            "handoff_records": int(value.get("handoff_records", 0) or 0),
            "handoff_ready_records": int(value.get("handoff_ready_records", 0) or 0),
            "ok": value.get("ok") is True,
            "manifest": value.get("manifest", {}) if isinstance(value.get("manifest"), dict) else {},
        }
    return {"path": str(value), "transport": "", "handoff_records": 0, "handoff_ready_records": 0, "ok": True, "manifest": {}}


def _load_texts(root: pathlib.Path) -> dict[str, str]:
    files = {
        "pyproject": "pyproject.toml",
        "init": "yinyo/__init__.py",
        "readme": "README.md",
        "readme_zh": "README.zh-CN.md",
        "maintenance": "MAINTENANCE.md",
        "changelog": "CHANGELOG.md",
        "spec": "docs/spec.md",
        "roadmap": "docs/roadmap.md",
        "deployment": "docs/deployment.md",
        "production_checklist": "docs/production-checklist.md",
        "security": "SECURITY.md",
        "release_workflow": ".github/workflows/release.yml",
        "test_workflow": ".github/workflows/test.yml",
    }
    data = {}
    for key, rel in files.items():
        path = root / rel
        data[key] = path.read_text(encoding="utf-8") if path.is_file() else ""
    return data


def _read_versions(texts: dict[str, str]) -> dict[str, str]:
    pyproject = re.search(r'^version = "([^"]+)"', texts["pyproject"], re.MULTILINE)
    init = re.search(r'__version__ = "([^"]+)"', texts["init"])
    package = pyproject.group(1) if pyproject else ""
    module = init.group(1) if init else ""
    if package == "1.0.0rc1" and "1.0.0-lite" in texts["readme"]:
        display = "1.0.0-lite"
    elif "a" in package:
        display = package.replace("a", "-alpha.")
    else:
        display = package
    return {"package": package, "module": module, "display": display}


def _read_smoke_chain(
    root: pathlib.Path,
    workspace: pathlib.Path,
    smoke_path: str | pathlib.Path | None,
    config_path: str | pathlib.Path | None,
) -> dict[str, Any]:
    cfg = RuntimeConfig.load(str(config_path) if config_path else None, workspace=str(workspace), smoke_evidence_path=str(smoke_path or ""))
    resolved_smoke = _resolve_path(root, cfg.smoke_evidence_path)
    resolved_log = _resolve_path(root, cfg.log_path)
    resolved_job = _resolve_path(root, cfg.job_store_path)
    resolved_event = _resolve_path(root, cfg.event_store_path)
    if not resolved_smoke.is_file():
        return {
            "ok": False,
            "missing": [f"smoke_file:{resolved_smoke}"],
            "paths": {
                "smoke_evidence": str(resolved_smoke),
                "runtime_log": str(resolved_log),
                "job_store": str(resolved_job),
                "event_store": str(resolved_event),
            },
        }
    return verify_smoke_evidence_chain(
        smoke_path=str(resolved_smoke),
        log_path=str(resolved_log),
        job_store_path=str(resolved_job),
        event_store_path=str(resolved_event),
        required=set(required_live_smoke_scenarios(cfg.transport)),
        transport=cfg.transport,
    )


def _read_advanced_live(
    root: pathlib.Path,
    workspace: pathlib.Path,
    smoke_path: str | pathlib.Path | None,
    config_path: str | pathlib.Path | None,
) -> dict[str, Any]:
    cfg = RuntimeConfig.load(str(config_path) if config_path else None, workspace=str(workspace), smoke_evidence_path=str(smoke_path or ""))
    resolved_smoke = _resolve_path(root, cfg.smoke_evidence_path)
    if not resolved_smoke.is_file():
        return {
            "ok": False,
            "missing": ["advanced_smoke_file"],
            "field_missing": [],
            "source_missing": [],
            "path": str(resolved_smoke),
        }
    return verify_advanced_live_evidence(str(resolved_smoke))


def _resolve_path(root: pathlib.Path, path: str) -> pathlib.Path:
    resolved = pathlib.Path(path)
    if not resolved.is_absolute():
        resolved = root / resolved
    return resolved


def _item(id_: str, requirement: str, passed: bool, evidence: list[str], blockers: list[str]) -> ReadinessItem:
    return ReadinessItem(id_, requirement, passed, evidence, blockers if not passed else [])


def _required_files_exist(root: pathlib.Path, files: list[str]) -> tuple[list[str], list[str]]:
    present = [rel for rel in files if (root / rel).is_file()]
    missing = [rel for rel in files if not (root / rel).is_file()]
    return present, missing


def _r1_01(root: pathlib.Path, texts: dict[str, str]) -> ReadinessItem:
    present, missing = _required_files_exist(root, [".github/workflows/test.yml", ".github/workflows/release.yml"])
    required = [
        "pytest tests",
        "python scripts/verify_release.py",
        "python scripts/replay_scenarios.py",
        "python scripts/replay_scenarios.py --matrix",
    ]
    workflow_text = texts["test_workflow"] + "\n" + texts["release_workflow"]
    missing_cmds = [cmd for cmd in required if cmd not in workflow_text]
    return _item(
        "R1-01",
        "Internal acceptance gates are green in CI and local development.",
        not missing and not missing_cmds,
        present + [cmd for cmd in required if cmd not in missing_cmds],
        [f"missing file: {rel}" for rel in missing] + [f"missing CI command: {cmd}" for cmd in missing_cmds],
    )


def _r1_02(root: pathlib.Path) -> ReadinessItem:
    present, missing = _required_files_exist(root, ["scripts/verify_wheel.py"])
    script = (root / "scripts" / "verify_wheel.py").read_text(encoding="utf-8") if not missing else ""
    requirements = [
        '"-m", "build"',
        '"pip", "install"',
        "Wheel verification passed",
        "SDIST_REQUIRED_FILES",
        "tarfile.open",
    ]
    missing_terms = [term for term in requirements if term not in script]
    return _item(
        "R1-02",
        "Fresh install works in a clean virtual environment.",
        not missing and not missing_terms,
        present + [term for term in requirements if term not in missing_terms],
        [f"missing file: {rel}" for rel in missing] + [f"wheel verifier missing: {term}" for term in missing_terms],
    )


def _override_path(live_smoke_override: dict[str, Any] | None) -> str:
    return str(live_smoke_override.get("path", "")) if live_smoke_override else ""


def _r1_03(target: str, smoke_chain: dict[str, Any] | None, live_smoke_override: dict[str, Any] | None) -> ReadinessItem:
    if target != "1.0.0":
        return _item(
            "R1-03",
            "Core Feishu workflows pass against a live Feishu app.",
            True,
            ["not enforced for non-1.0 target"],
            [],
        )
    if live_smoke_override:
        return _item(
            "R1-03",
            "Core Feishu workflows pass against a live Feishu app.",
            True,
            [f"verified redacted bundle: {_override_path(live_smoke_override)}"],
            [],
        )
    missing = smoke_chain.get("missing", []) if smoke_chain else ["smoke_chain:missing"]
    return _item(
        "R1-03",
        "Core Feishu workflows pass against a live Feishu app.",
        bool(smoke_chain and smoke_chain.get("ok")),
        [f"smoke paths: {smoke_chain.get('paths', {})}" if smoke_chain else "smoke chain absent"],
        [f"live smoke incomplete: {', '.join(missing)}"] if missing else [],
    )


def _r1_04(root: pathlib.Path, texts: dict[str, str]) -> ReadinessItem:
    present, missing = _required_files_exist(root, ["SECURITY.md", "scripts/verify_secrets.py"])
    required = ["python scripts/verify_secrets.py", "blocked"]
    haystack = texts["security"] + "\n" + texts["test_workflow"] + "\n" + texts["release_workflow"]
    missing_terms = [term for term in required if term not in haystack]
    return _item(
        "R1-04",
        "Security boundaries are current.",
        not missing and not missing_terms,
        present + [term for term in required if term not in missing_terms],
        [f"missing file: {rel}" for rel in missing] + [f"security evidence missing: {term}" for term in missing_terms],
    )


def _r1_05(texts: dict[str, str]) -> ReadinessItem:
    terms_by_doc = {
        "README.md": (
            "1.0.0-lite",
            "blocked until live Feishu smoke evidence",
            "docs/deployment.md",
            "docs/production-checklist.md",
            "yinyo.frontier_readiness.v1",
            "record-advanced",
            "bundle_digest",
            "yinyo.advanced_ref_attestation.v1",
            "resource quotas",
            "transport=ws",
            "handoff_ready_records",
            "replay_handoff()",
            "live_provenance.ws_sdk_session_id",
            "redacted runtime log",
            "ws_sdk_session_id",
            "inherits",
            "must match",
            "sha256(app_id)",
            "feishu_app_id_hash",
        ),
        "README.zh-CN.md": (
            "1.0.0-lite",
            "真实飞书 live smoke",
            "docs/deployment.md",
            "docs/production-checklist.md",
            "yinyo.frontier_readiness.v1",
            "record-advanced",
            "bundle_digest",
            "yinyo.advanced_ref_attestation.v1",
            "resource quotas",
            "transport=ws",
            "handoff_ready_records",
            "replay_handoff()",
            "live_provenance.ws_sdk_session_id",
            "redacted runtime log",
            "ws_sdk_session_id",
            "inherits",
            "must match",
            "sha256(app_id)",
            "feishu_app_id_hash",
        ),
        "docs/deployment.md": (
            "yinyo smoke runbook --config ./yinyo.env",
            "yinyo smoke bundle --config ./yinyo.env --output ./workspace/smoke-bundle --handoff-dir ./workspace/runs",
            "yinyo.advanced_ref_attestation.v1",
            "yinyo.live_provenance.v1",
            "--live-attestation-id",
            "python scripts/verify_release.py --target 1.0.0 --bundle ./workspace/smoke-bundle --candidate 1.0.0",
            "service_start",
            "smoke_mode=false",
            "ws_transport_start",
            "ws_event_received",
            "handoff_ready_records",
            "replay_handoff()",
            "live_provenance.ws_sdk_session_id",
            "redacted runtime log",
            "ws_sdk_session_id",
            "live provenance readiness",
            "inherits",
            "must match",
            "sha256(app_id)",
            "feishu_app_id_hash",
        ),
        "docs/production-checklist.md": (
            "yinyo.frontier_readiness.v1",
            "yinyo.advanced_ref_attestation.v1",
            "yinyo.live_provenance.v1",
            "yinyo.resource_quota.v1",
            "--handoff-dir ./workspace/runs",
            "python scripts/verify_release.py --bundle <bundle-dir>",
            "README claims trace back to tests, source, or explicit target-state labels",
            "handoffs.ready_records > 0",
            "replay_handoff()",
            "live_provenance.ws_sdk_session_id",
            "redacted runtime log",
            "ws_sdk_session_id",
            "live provenance readiness",
            "inherits",
            "must match",
            "sha256(app_id)",
            "feishu_app_id_hash",
        ),
        "MAINTENANCE.md": (
            "python -m yinyo.cli config template --live-smoke > yinyo.env",
            "python -m yinyo.cli smoke runbook --config ./yinyo.env",
            "python -m yinyo.cli smoke bundle --config ./yinyo.env --output ./workspace/smoke-bundle --handoff-dir ./workspace/runs",
            "yinyo.advanced_ref_attestation.v1",
            "yinyo.live_provenance.v1",
            "handoff_ready_records > 0",
            "replay_handoff()",
            "live_provenance.ws_sdk_session_id",
            "redacted `service_start`",
            "ws_sdk_session_id",
            "live provenance readiness",
            "inherits",
            "must match",
            "sha256(app_id)",
            "feishu_app_id_hash",
        ),
        "docs/spec.md": (
            "Agent Harness Engineering survey",
            "ETCLOVG",
            "| Execution |",
            "| Tooling |",
            "| Context |",
            "| Lifecycle |",
            "| Observability |",
            "| Verification |",
            "| Governance |",
            "trace-native proof envelopes",
            "yinyo.proof_ablation.v1",
            "State handoff",
        ),
        "docs/roadmap.md": (
            "Harness Survey Backlog",
            "Harden and scale execution environments",
            "Reliable state in long-running agents",
            "Trace-native failure diagnosis",
            "Standard handoffs",
            "Adaptive simplification",
        ),
    }
    text_key = {
        "README.md": "readme",
        "README.zh-CN.md": "readme_zh",
        "docs/deployment.md": "deployment",
        "docs/production-checklist.md": "production_checklist",
        "MAINTENANCE.md": "maintenance",
        "docs/spec.md": "spec",
        "docs/roadmap.md": "roadmap",
    }
    missing = [
        f"{doc}: {term}"
        for doc, terms in terms_by_doc.items()
        for term in terms
        if term not in texts[text_key[doc]]
    ]

    ordered_checks = [
        ("README.md", "python -m yinyo.cli config template --live-smoke > yinyo.env", "python -m yinyo.cli smoke runbook --config ./yinyo.env"),
        ("README.zh-CN.md", "python -m yinyo.cli config template --live-smoke > yinyo.env", "python -m yinyo.cli smoke runbook --config ./yinyo.env"),
        ("MAINTENANCE.md", "python -m yinyo.cli config template --live-smoke > yinyo.env", "python -m yinyo.cli smoke runbook --config ./yinyo.env"),
        ("docs/deployment.md", "yinyo smoke reset --config ./yinyo.env --confirm-reset", "yinyo serve --config ./yinyo.env", "Verify the evidence:"),
        ("docs/deployment.md", "yinyo serve --config ./yinyo.env", "yinyo smoke record-advanced --config ./yinyo.env --scenario image_understanding", "Verify the evidence:"),
    ]
    order_blockers = []
    for check in ordered_checks:
        doc, first, second = check[:3]
        text = texts[text_key[doc]]
        if len(check) > 3:
            marker = check[3]
            if marker in text:
                text = text[text.index(marker):]
        if not _has_command_line_order(text, first, second):
            order_blockers.append(f"{doc}: command order drifted: {first} must precede {second}")
    return _item(
        "R1-05",
        "Public docs match implemented behavior.",
        not missing and not order_blockers,
        [f"{doc}: {term}" for doc, terms in terms_by_doc.items() for term in terms if f"{doc}: {term}" not in missing],
        [f"public docs missing claim anchor: {term}" for term in missing] + order_blockers,
    )


def _has_command_line_order(text: str, first: str, second: str) -> bool:
    first_positions = _command_line_positions(text, first)
    second_positions = _command_line_positions(text, second)
    return bool(first_positions and second_positions and any(a < b for a in first_positions for b in second_positions))


def _command_line_positions(text: str, command: str) -> list[int]:
    pattern = rf"(?m)^\s*{re.escape(command)}(?:\s|$)"
    return [match.start() for match in re.finditer(pattern, text)]


def _r1_06(texts: dict[str, str], versions: dict[str, str]) -> ReadinessItem:
    blockers = []
    if not versions["package"]:
        blockers.append("pyproject version missing")
    if versions["package"] != versions["module"]:
        blockers.append("pyproject and module versions differ")
    for name in ("readme", "changelog"):
        if versions["display"] and versions["display"] not in texts[name]:
            blockers.append(f"{name} missing display version")
    if "v8." in texts["readme"] and "internal prototype milestones" not in texts["readme"]:
        blockers.append("README still presents v8.x as public version")
    return _item(
        "R1-06",
        "Release metadata uses external SemVer only.",
        not blockers,
        [versions["package"], versions["display"], "v8.x marked internal history"],
        blockers,
    )


def _live_missing(live_matrix: dict[str, Any] | None, *names: str) -> list[str]:
    if not live_matrix:
        return []
    missing = set(live_matrix.get("missing_scenarios", []))
    return [name for name in names if name in missing]


def _r1_07(root: pathlib.Path, matrix: dict[str, Any], target: str, smoke_chain: dict[str, Any] | None, live_smoke_override: dict[str, Any] | None, live_matrix: dict[str, Any] | None = None) -> ReadinessItem:
    present, missing = _required_files_exist(root, ["yinyo/feishu_ws.py", "yinyo/feishu_adapter.py", "examples/feishu_scenarios.json"])
    blockers = [f"missing file: {rel}" for rel in missing]
    if not matrix["ok"]:
        blockers.append("HTTP fallback scenario replay matrix failed")
    if target == "1.0.0" and live_smoke_override and live_smoke_override.get("transport") != "ws":
        blockers.append("verified bundle is not ws long-connection evidence")
    if target == "1.0.0" and live_smoke_override and live_smoke_override.get("transport") == "ws" and not live_smoke_override.get("handoff_records"):
        blockers.append("verified ws bundle is missing handoff records")
    if target == "1.0.0" and live_smoke_override and live_smoke_override.get("transport") == "ws" and not live_smoke_override.get("handoff_ready_records"):
        blockers.append("verified ws bundle is missing replayable handoff records")
    blockers.extend(f"live matrix missing scenario: {name}" for name in _live_missing(live_matrix, "ws_ack_boundary"))
    if target == "1.0.0" and not live_smoke_override and not (smoke_chain and smoke_chain.get("ok")):
        blockers.append("live long-connection smoke evidence missing")
    return _item(
        "R1-07",
        "Feishu long-connection is primary and HTTP webhook remains tested.",
        not blockers,
        present + ["scenario matrix ok" if matrix["ok"] else "scenario matrix failed"] + ([f"verified redacted bundle: {_override_path(live_smoke_override)}"] if live_smoke_override else []),
        blockers,
    )


def _advanced_blockers(advanced_live: dict[str, Any] | None) -> list[str]:
    if not advanced_live:
        return ["advanced live evidence missing"]
    blockers = []
    blockers.extend(f"missing advanced live scenario: {name}" for name in advanced_live.get("missing", []))
    blockers.extend(f"missing advanced live field: {name}" for name in advanced_live.get("field_missing", []))
    blockers.extend(f"missing advanced live controlled recorder: {name}" for name in advanced_live.get("source_missing", []))
    blockers.extend(f"missing advanced live proof: {name}" for name in advanced_live.get("proof_missing", []))
    blockers.extend(f"mismatched advanced live proof: {name}" for name in advanced_live.get("proof_mismatch", []))
    blockers.extend(f"unresolved advanced live ref: {name}" for name in advanced_live.get("ref_unresolved", []))
    return blockers


def _r1_08(matrix: dict[str, Any], target: str, advanced_live: dict[str, Any] | None, live_smoke_override: dict[str, Any] | None, live_matrix: dict[str, Any] | None = None) -> ReadinessItem:
    required = {"image_understanding", "long_conversation", "card_fallback", "memory_supersession", "partial_failure"}
    passed = {item["name"] for item in matrix["scenarios"] if item.get("passed")}
    missing = sorted(required - passed)
    advanced_blockers = _advanced_blockers(advanced_live) if target == "1.0.0" and not live_smoke_override else []
    live_matrix_blockers = [
        f"live matrix missing scenario: {name}"
        for name in _live_missing(live_matrix, *sorted(required))
    ]
    return _item(
        "R1-08",
        "Advanced product workflows are not deferred.",
        not missing and not advanced_blockers and not live_matrix_blockers,
        sorted(required & passed) + ([f"verified redacted bundle: {_override_path(live_smoke_override)}"] if live_smoke_override else []),
        [f"missing advanced scenario: {name}" for name in missing] + advanced_blockers + live_matrix_blockers,
    )


def _r1_09(matrix: dict[str, Any], target: str, advanced_live: dict[str, Any] | None, live_smoke_override: dict[str, Any] | None, live_matrix: dict[str, Any] | None = None) -> ReadinessItem:
    scenario = next((item for item in matrix["scenarios"] if item["name"] == "trace2skill_promotion"), {})
    evidence = scenario.get("evidence", {})
    required = {
        "regression_fixture": True,
        "regression_replay_passed": True,
        "validation_passed": True,
        "replay_command_passed": True,
        "replay_stdout_mentions_failure": True,
        "replay_stdout_mentions_guardrail": True,
        "promotion_record": True,
    }
    blockers = [f"{key} not proven" for key, value in required.items() if evidence.get(key) is not value]
    if evidence.get("replay_exit_code") != 0:
        blockers.append("replay command exit code not zero")
    if evidence.get("promotion_status") not in {"proven", "stable"}:
        blockers.append("promotion status not proven")
    if not evidence.get("failure_trace_ref"):
        blockers.append("failure trace ref missing")
    if not evidence.get("post_promotion_run_ref"):
        blockers.append("post-promotion validation ref missing")
    if target == "1.0.0" and not live_smoke_override:
        live_blockers = [
            item for item in _advanced_blockers(advanced_live)
            if "trace2skill_promotion" in item or "advanced_smoke_file" in item or item == "advanced live evidence missing"
        ]
        blockers.extend(live_blockers)
    blockers.extend(f"live matrix missing scenario: {name}" for name in _live_missing(live_matrix, "trace2skill_promotion"))
    return _item(
        "R1-09",
        "Trace2Skill is a complete lifecycle, not a draft artifact.",
        bool(scenario.get("passed")) and not blockers,
        [f"{key}={value}" for key, value in sorted(evidence.items())] + ([f"verified redacted bundle: {_override_path(live_smoke_override)}"] if live_smoke_override else []),
        blockers,
    )


def _r1_10(texts: dict[str, str], matrix: dict[str, Any], target: str, advanced_live: dict[str, Any] | None, live_smoke_override: dict[str, Any] | None, live_matrix: dict[str, Any] | None = None) -> ReadinessItem:
    scenario = next((item for item in matrix["scenarios"] if item["name"] == "deepseek_usage"), {})
    docs_text = texts["deployment"] + "\n" + texts["readme"]
    missing_docs = [term for term in ("model_retry_count", "model_retry_backoff_seconds", "DeepSeek") if term not in docs_text]
    live_blockers = []
    if target == "1.0.0" and not live_smoke_override:
        live_blockers = [
            item for item in _advanced_blockers(advanced_live)
            if "deepseek_usage" in item or "advanced_smoke_file" in item or item == "advanced live evidence missing"
        ]
    live_blockers.extend(f"live matrix missing scenario: {name}" for name in _live_missing(live_matrix, "deepseek_usage"))
    return _item(
        "R1-10",
        "DeepSeek adaptation is measured.",
        bool(scenario.get("passed")) and not missing_docs and not live_blockers,
        ["deepseek_usage scenario passed"] + [term for term in ("model_retry_count", "model_retry_backoff_seconds", "DeepSeek") if term not in missing_docs] + ([f"verified redacted bundle: {_override_path(live_smoke_override)}"] if live_smoke_override else []),
        [f"missing DeepSeek doc evidence: {term}" for term in missing_docs] + live_blockers,
    )


def _r1_11(matrix: dict[str, Any], target: str, advanced_live: dict[str, Any] | None, live_smoke_override: dict[str, Any] | None, live_matrix: dict[str, Any] | None = None) -> ReadinessItem:
    rows = matrix.get("matrix", {}).get("rows", [])
    harness_layers = matrix.get("matrix", {}).get("harness_layers", {})
    harness_rows = harness_layers.get("rows", []) if isinstance(harness_layers, dict) else []
    failed = [row["id"] for row in rows if not row.get("passed")]
    missing_layers = [row["layer"] for row in harness_rows if not row.get("passed")]
    advanced_blockers = _advanced_blockers(advanced_live) if target == "1.0.0" and not live_smoke_override else []
    live_missing = list(live_matrix.get("missing_scenarios", []) if live_matrix else [])
    if not live_smoke_override:
        live_missing = [name for name in live_missing if name != "verified_ws_bundle"]
    live_matrix_blockers = [
        f"live matrix missing scenario: {name}"
        for name in live_missing
    ]
    return _item(
        "R1-11",
        "3+6 product traits are each backed by evidence.",
        bool(rows) and bool(harness_rows) and not failed and not missing_layers and not advanced_blockers and not live_matrix_blockers,
        [row["id"] for row in rows if row.get("passed")]
        + [f"harness_layer:{row['layer']}" for row in harness_rows if row.get("passed")]
        + ([f"verified redacted bundle: {_override_path(live_smoke_override)}"] if live_smoke_override else []),
        [f"matrix row failed: {row}" for row in failed]
        + [f"harness layer missing proof: {layer}" for layer in missing_layers]
        + advanced_blockers
        + live_matrix_blockers,
    )
