"""Documentation release-flow checks."""

from __future__ import annotations

import pathlib
import re


ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_candidate_readme_commands_create_config_before_runbook():
    for readme in ("README.md", "README.zh-CN.md", "MAINTENANCE.md"):
        text = (ROOT / readme).read_text(encoding="utf-8")
        template = "python -m yinyo.cli config template --live-smoke > yinyo.env"
        runbook = "python -m yinyo.cli smoke runbook --config ./yinyo.env"

        assert template in text
        assert runbook in text
        assert text.index(template) < text.index(runbook)
        assert "--transport http" not in text


def test_candidate_flow_starts_service_before_advanced_records():
    for doc in ("README.md", "README.zh-CN.md", "docs/production-checklist.md", "MAINTENANCE.md"):
        text = (ROOT / doc).read_text(encoding="utf-8")
        reset = "python -m yinyo.cli smoke reset --config ./yinyo.env --confirm-reset"
        serve = "python -m yinyo.cli serve --config ./yinyo.env"
        advanced = "python -m yinyo.cli smoke record-advanced --config ./yinyo.env --scenario image_understanding"
        wait = "python -m yinyo.cli smoke wait --config ./yinyo.env"

        assert reset in text
        assert serve in text
        assert advanced in text
        assert wait in text
        assert text.index(reset) < text.index(serve) < text.index(advanced) < text.index(wait)


def test_candidate_flow_promotes_metadata_after_bundle_gate():
    docs = ("README.md", "README.zh-CN.md", "MAINTENANCE.md", "docs/deployment.md", "docs/production-checklist.md", "docs/versioning.md")
    dry_run = "python scripts/prepare_release_metadata.py --version 1.0.0 --verified-bundle"
    apply = "python scripts/prepare_release_metadata.py --version 1.0.0 --verified-bundle"
    candidate = "python scripts/verify_release.py --target 1.0.0 --bundle"

    for doc in docs:
        text = (ROOT / doc).read_text(encoding="utf-8")
        assert dry_run in text
        assert "--apply" in text
        assert "--verified-bundle" in text
        assert candidate in text

    for doc in ("README.md", "README.zh-CN.md", "MAINTENANCE.md", "docs/deployment.md"):
        text = (ROOT / doc).read_text(encoding="utf-8")
        first_candidate = text.index("python scripts/verify_release.py --target 1.0.0 --bundle")
        metadata = text.index("python scripts/prepare_release_metadata.py --version 1.0.0 --verified-bundle")
        assert first_candidate < metadata


def test_deployment_smoke_sequence_does_not_record_advanced_before_live_run():
    text = (ROOT / "docs" / "deployment.md").read_text(encoding="utf-8")
    marker = "Verify the evidence:"
    serve = "yinyo serve --config ./yinyo.env"
    live_actions = "Keep the service process running while you perform the real Feishu text, image,"
    advanced = "yinyo smoke record-advanced --config ./yinyo.env --scenario image_understanding"

    assert marker in text
    flow = text[text.index(marker):]
    assert serve in flow
    assert live_actions in flow
    assert advanced in flow
    assert flow.index(serve) < flow.index(live_actions) < flow.index(advanced)


def test_maintenance_release_gate_uses_real_wait_timeout():
    text = (ROOT / "MAINTENANCE.md").read_text(encoding="utf-8")

    assert "python -m yinyo.cli smoke wait --config ./yinyo.env" in text
    assert "smoke wait --config ./yinyo.env --timeout 0" not in text


def test_readme_test_badges_match_current_local_count():
    expected = "tests-355%20local"
    for readme in ("README.md", "README.zh-CN.md"):
        text = (ROOT / readme).read_text(encoding="utf-8")
        assert expected in text

    for doc in ("CHANGELOG.md", "docs/roadmap.md"):
        text = (ROOT / doc).read_text(encoding="utf-8")
        assert "355" in text
        for stale in ("354", "353", "352", "350", "347", "330", "302", "293", "292", "291", "283", "282", "280", "278", "276", "274", "263", "262", "261", "260", "258", "256 tests", "256 local tests", "253", "252", "251", "249", "248", "247", "215", "221", "222", "223", "224", "225"):
            assert stale not in text


def test_lite_release_version_surfaces_are_consistent():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    init = (ROOT / "yinyo" / "__init__.py").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    zh_readme = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    versioning = (ROOT / "docs" / "versioning.md").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    assert 'version = "1.0.0rc1"' in pyproject
    assert '__version__ = "1.0.0rc1"' in init
    assert "YINYO 1.0.0-lite" in init
    assert "version-1.0.0--lite-2ea043" in readme
    assert "Current external version: `1.0.0-lite`" in readme
    assert "Python package version: `1.0.0rc1`" in readme
    assert "当前外部版本：`1.0.0-lite`" in zh_readme
    assert "Python 包版本：`1.0.0rc1`" in zh_readme
    assert changelog.index("## 1.0.0-lite") < changelog.index("## 0.1.0-alpha.1")
    assert "| Product version | `1.0.0-lite` |" in versioning
    assert "| Python package version | `1.0.0rc1` |" in versioning
    assert "v1.0.0-lite" in versioning
    assert 'default: "1.0.0-lite"' in workflow


def test_public_docs_do_not_contain_common_mojibake():
    docs = [
        "README.md",
        "README.zh-CN.md",
        "AGENTS.md",
        "CONTRIBUTING.md",
        "MAINTENANCE.md",
        "SECURITY.md",
        "CHANGELOG.md",
        "docs/architecture.md",
        "docs/deployment.md",
        "docs/benchmarking.md",
        "docs/external-testing.md",
        "docs/release-evidence-matrix.md",
        "docs/production-checklist.md",
        "docs/roadmap.md",
        "docs/spec.md",
        "docs/versioning.md",
    ]
    bad_fragments = ["\ufffd", "\\ufffd", "??", "鎼", "闵", "閵", "濞"]
    for doc in docs:
        text = (ROOT / doc).read_text(encoding="utf-8")
        for fragment in bad_fragments:
            assert fragment not in text, f"{doc} contains mojibake fragment {fragment!r}"


def test_public_docs_relative_links_resolve():
    docs = [
        "README.md",
        "README.zh-CN.md",
        "MAINTENANCE.md",
        "docs/deployment.md",
        "docs/production-checklist.md",
    ]
    ignored_schemes = ("http://", "https://", "mailto:", "file:")

    for doc in docs:
        path = ROOT / doc
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", text):
            target = match.group(1).strip()
            target = target.split()[0].strip("<>")
            if not target or target.startswith("#") or target.startswith(ignored_schemes):
                continue
            target_path = target.split("#", 1)[0]
            if not target_path:
                continue
            resolved = (path.parent / target_path).resolve()
            assert resolved.exists(), f"{doc} has broken relative link: {target}"


def test_python_support_matrix_is_consistent():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    ci = (ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
    deployment = (ROOT / "docs" / "deployment.md").read_text(encoding="utf-8")

    for version in ("3.11", "3.12", "3.13"):
        assert f'"Programming Language :: Python :: {version}"' in pyproject
        assert version in ci
        assert version in deployment


def test_public_docs_preserve_harness_positioning_and_frontier_boundaries():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    zh_readme = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    spec = (ROOT / "docs" / "spec.md").read_text(encoding="utf-8")

    assert "harness Agent" in readme
    assert "Hermes and OpenClaw" in readme
    assert "docs/benchmarking.md" in readme
    assert "docs/release-evidence-matrix.md" in readme
    assert "harness Agent" in zh_readme
    assert "Hermes" in zh_readme and "OpenClaw" in zh_readme
    assert "docs/benchmarking.md" in zh_readme
    assert "docs/release-evidence-matrix.md" in zh_readme
    assert "## Product Constitution" in readme
    assert "## 产品宪法" in zh_readme
    assert "## Frontier Mechanism Map" in spec
    assert "The local release matrix proves harness mechanisms" in spec
    assert "yinyo.harness_layers.v1" in spec
    assert "versioned harness corpus" in spec


def test_spec_tracks_agent_harness_engineering_survey_alignment():
    spec = (ROOT / "docs" / "spec.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "docs" / "roadmap.md").read_text(encoding="utf-8")
    handoff = (ROOT / "docs" / "handoff.md").read_text(encoding="utf-8")
    evidence_matrix = (ROOT / "docs" / "release-evidence-matrix.md").read_text(encoding="utf-8")

    assert "## Harness Engineering Alignment" in spec
    assert "https://picrew.github.io/LLM-Harness/" in spec
    for layer in ("Execution", "Tooling", "Context", "Lifecycle", "Observability", "Verification", "Governance"):
        assert layer in spec
    assert "trace-native proof envelopes" in roadmap
    assert "ETCLOVG layer coverage table" in spec
    assert "handoff packets" in roadmap
    assert "handoff.json" in handoff
    assert "read as of 2026-05-29" in evidence_matrix
    for layer in ("Execution", "Tooling", "Context", "Lifecycle", "Observability", "Verification", "Governance"):
        assert layer in evidence_matrix


def test_readmes_have_equivalent_1_0_evidence_chain_boundaries():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    zh_readme = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")

    for token in ("runtime logs", "durable job", "event idempotency", "single-writer runtime lock", "service_start", "ws_transport_start", "ws_event_received", "ACK metrics", "bundle_digest", "transport=ws", "record-advanced", "live_provenance.ws_sdk_session_id", "ws_sdk_session_id", "redacted runtime log"):
        assert token in readme
    for token in ("runtime logs", "durable job", "event idempotency", "single-writer runtime lock", "service_start", "ws_transport_start", "ws_event_received", "ACK metrics", "bundle_digest", "transport=ws", "record-advanced", "live_provenance.ws_sdk_session_id", "ws_sdk_session_id", "redacted runtime log"):
        assert token in zh_readme


def test_release_docs_include_live_provenance_bundle_flags():
    docs = (
        "README.md",
        "README.zh-CN.md",
        "MAINTENANCE.md",
        "docs/deployment.md",
        "docs/external-testing.md",
        "docs/production-checklist.md",
    )
    for doc in docs:
        text = (ROOT / doc).read_text(encoding="utf-8")
        for token in ("--live-attestation-id", "--tenant-hash", "live_provenance.ws_sdk_session_id", "ws_sdk_session_id", "feishu_app_id_hash", "sha256(app_id)"):
            assert token in text, f"{doc} missing {token}"
    for doc in ("MAINTENANCE.md", "docs/deployment.md", "docs/production-checklist.md"):
        text = (ROOT / doc).read_text(encoding="utf-8")
        assert "inherits" in text and "--ws-sdk-session-id" in text and "must match" in text
        assert "sha256(app_id)" in text and "--feishu-app-id-hash" in text


def test_public_tree_verifier_is_documented_and_in_ci():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    zh_readme = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    maintenance = (ROOT / "MAINTENANCE.md").read_text(encoding="utf-8")
    versioning = (ROOT / "docs" / "versioning.md").read_text(encoding="utf-8")
    ci = (ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    verifier = (ROOT / "scripts" / "verify_public_tree.py").read_text(encoding="utf-8")

    for text in (readme, zh_readme, maintenance, versioning, ci, release):
        assert "python scripts/verify_public_tree.py" in text
    for token in ("prune workspace", "prune dist", "global-exclude *.env", "global-exclude *.runtime.jsonl"):
        assert token in manifest
    for token in ("yinyo/SOUL.md", "yinyo/AGENTS.md", "SOUL.md"):
        assert token in verifier


def test_external_testing_guide_is_linked_and_keeps_lite_boundary():
    guide = (ROOT / "docs" / "external-testing.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    zh_readme = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    versioning = (ROOT / "docs" / "versioning.md").read_text(encoding="utf-8")
    handoff = (ROOT / "docs" / "handoff.md").read_text(encoding="utf-8")

    assert "docs/external-testing.md" in readme
    assert "docs/external-testing.md" in zh_readme
    assert "docs/release-evidence-matrix.md" in readme
    assert "docs/benchmarking.md" in readme
    assert "1.0.0-lite" in guide
    assert "1.0.0rc1" in guide
    assert "not the full" in guide and "stable `1.0.0` release" in guide
    assert "python scripts/verify_release.py --target 1.0.0 --bundle <bundle-dir> --candidate 1.0.0" in guide
    assert "smoke-bundle" in guide
    assert "Do Not Share" in guide
    assert "External testers may run and report" in versioning
    assert "355 local tests" in handoff


def test_lite_release_notes_are_publishable_and_preserve_1_0_boundary():
    notes = (ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    zh_readme = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    maintenance = (ROOT / "MAINTENANCE.md").read_text(encoding="utf-8")
    versioning = (ROOT / "docs" / "versioning.md").read_text(encoding="utf-8")

    assert "RELEASE_NOTES.md" in readme
    assert "RELEASE_NOTES.md" in zh_readme
    assert "RELEASE_NOTES.md" in maintenance
    assert "RELEASE_NOTES.md" in versioning
    assert "# YINYO v1.0.0-lite" in notes
    assert "not the full stable `v1.0.0` release" in notes
    assert "yinyo_agent-1.0.0rc1-py3-none-any.whl" in notes
    assert "yinyo_agent-1.0.0rc1.tar.gz" in notes
    assert "python scripts/verify_release.py --target 1.0.0-lite --candidate 1.0.0-lite --json" in notes
    assert "python scripts/verify_release.py --target 1.0.0 --bundle <bundle-dir> --candidate 1.0.0" in notes
    assert "per-scenario `ws_event_received` ACK evidence" in notes
    assert "Do Not Attach" in notes
    assert "Do not attach stale alpha artifacts" in maintenance
    assert "python scripts/prepare_github_release.py --version v1.0.0-lite" in maintenance
    assert "python scripts/prepare_github_release.py --version v1.0.0-lite" in notes
    assert "docs/release-evidence-matrix.md" in notes
    assert "docs/benchmarking.md" in notes


def test_wheel_build_is_not_shadowed_by_local_build_directory_and_excludes_internal_package_docs():
    verifier = (ROOT / "scripts" / "verify_wheel.py").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")

    assert '"build", str(ROOT), "--outdir", str(ROOT / "dist")' in verifier
    assert 'cwd=build_cwd' in verifier
    assert 'yinyo = ["corpus/harness/*.json"]' in pyproject
    assert '[tool.setuptools.exclude-package-data]' in pyproject
    assert 'yinyo = ["*.md"]' in pyproject
    assert "recursive-include yinyo *.md" not in manifest
    assert "wheel contains internal package docs" in verifier
    assert "dist contains non-current YINYO release artifacts" in verifier


def test_github_release_preparation_script_is_documented_and_checksummed():
    script = (ROOT / "scripts" / "prepare_github_release.py").read_text(encoding="utf-8")
    verifier = (ROOT / "scripts" / "verify_wheel.py").read_text(encoding="utf-8")

    assert "yinyo.github_release.v1" in script
    assert "RELEASE_BODY.md" in script
    assert "SHA256SUMS.txt" in script
    assert "tag v1.0.0-lite does not point at HEAD" in script or "does not point at HEAD" in script
    assert "unexpected release assets in dist" in script
    assert "scripts/prepare_github_release.py" in verifier


def test_public_evidence_matrix_and_benchmarking_are_publishable():
    matrix = (ROOT / "docs" / "release-evidence-matrix.md").read_text(encoding="utf-8")
    benchmarking = (ROOT / "docs" / "benchmarking.md").read_text(encoding="utf-8")
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    maintenance = (ROOT / "MAINTENANCE.md").read_text(encoding="utf-8")
    deployment = (ROOT / "docs" / "deployment.md").read_text(encoding="utf-8")
    verifier = (ROOT / "scripts" / "verify_wheel.py").read_text(encoding="utf-8")

    for token in ("Less is more", "Borrow what works", "DeepSeek adapted", "Low ego, high drive", "verified ws bundle"):
        assert token in matrix
    for token in ("Execution", "Tooling", "Context", "Lifecycle", "Observability", "Verification", "Governance"):
        assert token in matrix
    assert "read as of 2026-05-29" in matrix
    assert "Hermes" in benchmarking and "OpenClaw" in benchmarking
    assert "does not claim to be more mature or more stable" in benchmarking
    assert "`1.0.0-lite` / `1.0.0rc1`" in security
    assert "`0.1.x-alpha` | Active alpha" not in security
    assert "diagnose --config ./yinyo.env" in maintenance
    assert "diagnose --workspace ./workspace" not in maintenance
    assert "advanced `<ref>` that looks like a local path must exist" in maintenance
    assert "durable operator attestation id" in maintenance
    assert "placeholders are rejected" in deployment
    assert "docs/release-evidence-matrix.md" in verifier
    assert "docs/benchmarking.md" in verifier
