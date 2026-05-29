"""Verify release metadata and evidence before tagging."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yinyo.readiness import audit_release_readiness
from yinyo.smoke import verify_live_provenance, verify_smoke_evidence_bundle


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify YINYO release readiness")
    parser.add_argument("--target", default="", help="Target external version, e.g. 1.0.0")
    parser.add_argument("--config", default="", help="Runtime config file used for 1.0 smoke evidence paths")
    parser.add_argument("--workspace", default=str(ROOT / "workspace"), help="Runtime workspace for 1.0 smoke evidence")
    parser.add_argument("--smoke-path", default="", help="Explicit smoke_evidence.jsonl path for 1.0 verification")
    parser.add_argument("--bundle", default="", help="Redacted smoke evidence bundle directory to verify")
    parser.add_argument("--candidate", default="", help="Optional external version being prepared for tag/publish")
    parser.add_argument("--json", action="store_true", help="Output machine-readable readiness audit")
    args = parser.parse_args()

    if args.config and args.bundle:
        print("FAIL: use either --config or --bundle for 1.0 evidence verification, not both", file=sys.stderr)
        return 2

    require_run_handoff = args.target == "1.0.0" and args.candidate == "1.0.0"
    bundle = verify_smoke_evidence_bundle(args.bundle, require_run_handoff=require_run_handoff) if args.bundle else None
    audit = audit_release_readiness(
        ROOT,
        target=args.target,
        live_smoke_override=_bundle_override(args.bundle, bundle),
        config_path=args.config or None,
        workspace=args.workspace,
        smoke_path=args.smoke_path or None,
    )
    failures = list(audit["failures"])
    if bundle:
        if not bundle["ok"]:
            failures.append("bundle: " + ", ".join(bundle["blockers"]))
        audit["bundle"] = bundle
        audit["ok"] = audit["ok"] and bundle["ok"]
        audit["failures"] = failures
    if args.candidate:
        candidate = _verify_candidate(args.candidate, audit, bundle)
        if not candidate["ok"]:
            failures.append("candidate: " + ", ".join(candidate["blockers"]))
        audit["candidate"] = candidate
        audit["ok"] = audit["ok"] and candidate["ok"]
        audit["failures"] = failures
    if args.json:
        print(json.dumps(audit, ensure_ascii=False, indent=2))
        return 0 if audit["ok"] else 1

    if failures:
        for failure in failures:
            print("FAIL:", failure)
        return 1

    print("Release verification passed")
    return 0


def _verify_candidate(candidate: str, audit: dict, bundle: dict | None) -> dict:
    blockers = []
    if candidate == "1.0.0-lite":
        versions = _read_candidate_versions()
        if versions["package"] != "1.0.0rc1":
            blockers.append(f"candidate 1.0.0-lite requires pyproject version 1.0.0rc1, found {versions['package'] or 'missing'}")
        if versions["module"] != "1.0.0rc1":
            blockers.append(f"candidate 1.0.0-lite requires module version 1.0.0rc1, found {versions['module'] or 'missing'}")
        if candidate not in versions["changelog_headings"]:
            blockers.append("candidate 1.0.0-lite requires changelog heading 1.0.0-lite")
        if audit.get("target") != "1.0.0-lite":
            blockers.append("candidate 1.0.0-lite requires --target 1.0.0-lite")
        if not audit.get("ok"):
            blockers.append("lite release readiness audit is not green")
    elif candidate == "1.0.0":
        versions = _read_candidate_versions()
        if versions["package"] != candidate:
            blockers.append(f"candidate 1.0.0 requires pyproject version {candidate}, found {versions['package'] or 'missing'}")
        if versions["module"] != candidate:
            blockers.append(f"candidate 1.0.0 requires module version {candidate}, found {versions['module'] or 'missing'}")
        if candidate not in versions["changelog_headings"]:
            blockers.append("candidate 1.0.0 requires changelog heading 1.0.0")
        if audit.get("target") != "1.0.0":
            blockers.append("candidate 1.0.0 requires --target 1.0.0")
        if not (bundle and bundle.get("ok")) and audit.get("smoke_chain_ok") is not True:
            blockers.append("candidate 1.0.0 requires verified live smoke evidence or verified bundle")
        if bundle:
            frontier = bundle.get("manifest", {}).get("frontier_readiness", {})
            if not isinstance(frontier, dict) or frontier.get("ok") is not True:
                blockers.append("candidate 1.0.0 requires frontier readiness in verified bundle")
        if bundle:
            transport = bundle.get("manifest", {}).get("runtime", {}).get("transport")
            if transport != "ws":
                blockers.append("candidate 1.0.0 requires a ws long-connection smoke bundle")
            handoff_records = bundle.get("manifest", {}).get("handoffs", {}).get("records", 0)
            handoff_ready_records = bundle.get("manifest", {}).get("handoffs", {}).get("ready_records", 0)
            if transport == "ws" and not handoff_records:
                blockers.append("candidate 1.0.0 requires run-level handoff.json in ws smoke bundle")
            if transport == "ws" and not handoff_ready_records:
                blockers.append("candidate 1.0.0 requires replayable run-level handoff in ws smoke bundle")
            provenance_blockers = _verify_live_provenance(bundle.get("manifest", {}))
            blockers.extend(provenance_blockers)
        if not audit.get("ok"):
            blockers.append("release readiness audit is not green")
    else:
        blockers.append(f"unsupported release candidate: {candidate}")
    return {
        "ok": not blockers,
        "version": candidate,
        "blockers": blockers,
        "requires_tag": f"v{candidate}",
    }


def _verify_live_provenance(manifest: dict) -> list[str]:
    blockers = verify_live_provenance(manifest, require_complete=True, prefix="candidate 1.0.0")
    return [
        "candidate 1.0.0 requires live provenance attestation in verified bundle"
        if blocker == "candidate 1.0.0 requires live provenance attestation"
        else blocker.replace("rejects placeholder live provenance fields", "requires live provenance fields")
        for blocker in blockers
    ]


def _read_candidate_versions() -> dict[str, object]:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    init = (ROOT / "yinyo" / "__init__.py").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    package = re.search(r'^version = "([^"]+)"', pyproject, re.MULTILINE)
    module = re.search(r'__version__ = "([^"]+)"', init)
    headings = re.findall(r"^##\s+\[?([0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.]+)?)\]?", changelog, re.MULTILINE)
    return {
        "package": package.group(1) if package else "",
        "module": module.group(1) if module else "",
        "changelog_headings": headings,
    }


def _bundle_override(path: str, bundle: dict | None) -> dict | None:
    if not (path and bundle and bundle.get("ok")):
        return None
    return {
        "path": path,
        "ok": bundle.get("ok") is True,
        "transport": bundle.get("manifest", {}).get("runtime", {}).get("transport", ""),
        "handoff_records": bundle.get("manifest", {}).get("handoffs", {}).get("records", 0),
        "handoff_ready_records": bundle.get("manifest", {}).get("handoffs", {}).get("ready_records", 0),
        "manifest": bundle.get("manifest", {}),
    }


if __name__ == "__main__":
    raise SystemExit(main())
