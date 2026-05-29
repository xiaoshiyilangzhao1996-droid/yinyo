"""Build and verify a clean wheel install."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
SUBPROCESS_TIMEOUT_SECONDS = 180
SDIST_REQUIRED_FILES = [
    "README.zh-CN.md",
    "SECURITY.md",
    "MAINTENANCE.md",
    "yinyo.env.example",
    ".github/workflows/release.yml",
    "docs/spec.md",
    "docs/deployment.md",
    "docs/release-evidence-matrix.md",
    "docs/benchmarking.md",
    "corpus/harness/scenarios.v1.json",
    "examples/feishu_scenarios.json",
    "scripts/verify_release.py",
    "scripts/verify_wheel.py",
    "scripts/prepare_github_release.py",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify YINYO wheel install smoke")
    parser.add_argument("--skip-build", action="store_true", help="Use an existing wheel in dist/")
    args = parser.parse_args()

    if not args.skip_build:
        with tempfile.TemporaryDirectory(prefix="yinyo-build-cwd-") as build_cwd:
            build = _run(
                [sys.executable, "-m", "build", str(ROOT), "--outdir", str(ROOT / "dist")],
                cwd=build_cwd,
                text=True,
            )
            if build.returncode != 0:
                return build.returncode

    expected_version = _expected_package_version()
    try:
        wheel, sdist = _select_release_artifacts(ROOT / "dist", expected_version)
    except ValueError as exc:
        print(f"FAIL: {exc}")
        return 1
    wheel_result = _verify_wheel_contents(wheel)
    if wheel_result:
        return wheel_result
    sdist_result = _verify_sdist(sdist)
    if sdist_result:
        return sdist_result

    with tempfile.TemporaryDirectory(prefix="yinyo-wheel-smoke-") as tmp:
        venv = pathlib.Path(tmp) / ".venv"
        _run([sys.executable, "-m", "venv", str(venv)], check=True)
        python = _venv_python(venv)
        _run([str(python), "-m", "pip", "install", "--quiet", str(wheel)], check=True)

        smoke = _run(
            [
                str(python),
                "-c",
                "import importlib.metadata as md; "
                f"expected_version = {expected_version!r}; "
                "meta = md.metadata('yinyo-agent'); "
                "assert meta['Name'] == 'yinyo-agent'; "
                "assert meta['Version'] == expected_version; "
                "assert meta['Summary'] == 'YINYO - a Feishu-native agent with memory, evidence, and release gates'; "
                "assert meta['Requires-Python'] == '>=3.11'; "
                "import yinyo; from yinyo import RuntimeConfig, JsonlJobQueue, RuntimeStoreLock, run_preflight, replay_handoff; "
                "from yinyo import build_smoke_evidence_status, load_harness_scenarios, record_advanced_live_evidence, verify_advanced_live_evidence, verify_full_smoke_evidence, verify_smoke_evidence_bundle, verify_smoke_evidence_file, audit_release_readiness; "
                "assert yinyo.__version__ == expected_version; "
                "assert 'long_conversation' in load_harness_scenarios(); "
                "print(yinyo.__version__, RuntimeConfig.__name__, JsonlJobQueue.__name__, RuntimeStoreLock.__name__, run_preflight.__name__, replay_handoff.__name__, "
                "build_smoke_evidence_status.__name__, load_harness_scenarios.__name__, record_advanced_live_evidence.__name__, verify_advanced_live_evidence.__name__, verify_full_smoke_evidence.__name__, verify_smoke_evidence_bundle.__name__, verify_smoke_evidence_file.__name__, audit_release_readiness.__name__)",
            ],
            cwd=tmp,
            text=True,
            capture_output=True,
            check=False,
        )
        if smoke.returncode != 0:
            print(smoke.stdout, end="")
            print(smoke.stderr, end="", file=sys.stderr)
            return smoke.returncode

        dry_run = _run(
            [str(python), "-m", "yinyo.cli", "serve", "--dry-run"],
            cwd=tmp,
            text=True,
            capture_output=True,
            check=False,
        )
        if dry_run.returncode != 2:
            print("FAIL: installed CLI dry-run should fail with missing config")
            print(dry_run.stdout, end="")
            print(dry_run.stderr, end="", file=sys.stderr)
            return 1

        workspace = pathlib.Path(tmp) / "workspace"
        config = pathlib.Path(tmp) / "yinyo.env"
        config.write_text(f"workspace={workspace}\ntransport=http\n", encoding="utf-8")
        _write_incomplete_runtime_evidence(workspace)
        command_checks = [
            {
                "name": "smoke plan",
                "cmd": [str(python), "-m", "yinyo.cli", "smoke", "plan", "--path", str(workspace / "smoke_evidence.jsonl")],
                "returncode": 0,
                "stdout": "YINYO 1.0 live smoke plan",
            },
            {
                "name": "smoke status reports incomplete evidence",
                "cmd": [str(python), "-m", "yinyo.cli", "smoke", "status", "--config", str(config), "--json"],
                "returncode": 1,
                "stdout": "\"next_actions\": [",
            },
            {
                "name": "smoke record advanced refuses incomplete evidence",
                "cmd": [
                    str(python),
                    "-m",
                    "yinyo.cli",
                    "smoke",
                    "record-advanced",
                    "--config",
                    str(config),
                    "--scenario",
                    "trace2skill_promotion",
                    "--json",
                ],
                "returncode": 2,
                "stderr": "missing required evidence fields",
            },
            {
                "name": "release json",
                "cmd": [str(python), "-m", "yinyo.cli", "config", "template", "--workspace", str(workspace)],
                "returncode": 0,
                "stdout": "runtime_lock_path",
            },
            {
                "name": "diagnose lifecycle",
                "cmd": [str(python), "-m", "yinyo.cli", "diagnose", "--config", str(config)],
                "returncode": 1,
                "stdout": "service: started=True, last_status=stopped",
            },
            {
                "name": "smoke bundle digest for incomplete evidence",
                "cmd": [
                    str(python),
                    "-m",
                    "yinyo.cli",
                    "smoke",
                    "bundle",
                    "--config",
                    str(config),
                    "--output",
                    str(pathlib.Path(tmp) / "bundle"),
                    "--json",
                ],
                "returncode": 1,
                "stdout": "bundle_digest",
            },
        ]
        for check in command_checks:
            result = _run(
                check["cmd"],
                cwd=tmp,
                text=True,
                capture_output=True,
                check=False,
            )
            stdout_ok = check.get("stdout", "") in result.stdout
            stderr_ok = check.get("stderr", "") in result.stderr
            expected_text_ok = stdout_ok and stderr_ok if check.get("stderr") else stdout_ok
            if result.returncode != check["returncode"] or not expected_text_ok:
                print(f"FAIL: installed CLI {check['name']} smoke failed")
                print(result.stdout, end="")
                print(result.stderr, end="", file=sys.stderr)
                return 1

    print(f"Wheel verification passed: {wheel.name}")
    return 0


def _expected_package_version() -> str:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    init = (ROOT / "yinyo" / "__init__.py").read_text(encoding="utf-8")
    package = re.search(r'^version = "([^"]+)"', pyproject, re.MULTILINE)
    module = re.search(r'__version__ = "([^"]+)"', init)
    package_version = package.group(1) if package else ""
    module_version = module.group(1) if module else ""
    if not package_version:
        raise RuntimeError("pyproject version missing")
    if package_version != module_version:
        raise RuntimeError(f"pyproject version {package_version} does not match yinyo.__version__ {module_version or 'missing'}")
    return package_version


def _select_release_artifacts(dist: pathlib.Path, expected_version: str) -> tuple[pathlib.Path, pathlib.Path]:
    expected_stem = f"yinyo_agent-{expected_version}"
    wheels = sorted(dist.glob("yinyo_agent-*.whl"), key=lambda path: path.name)
    sdists = sorted(dist.glob("yinyo_agent-*.tar.gz"), key=lambda path: path.name)
    if not wheels:
        raise ValueError("no yinyo_agent wheel found in dist/")
    if not sdists:
        raise ValueError("no yinyo_agent sdist found in dist/")
    stale = [
        path.name
        for path in [*wheels, *sdists]
        if not path.name.startswith(expected_stem)
    ]
    if stale:
        raise ValueError(f"dist contains non-current YINYO release artifacts: {', '.join(stale)}")
    matching_wheels = [path for path in wheels if path.name.startswith(expected_stem)]
    matching_sdists = [path for path in sdists if path.name.startswith(expected_stem)]
    if len(matching_wheels) != 1:
        raise ValueError(f"expected exactly one current wheel for {expected_version}, found {len(matching_wheels)}")
    if len(matching_sdists) != 1:
        raise ValueError(f"expected exactly one current sdist for {expected_version}, found {len(matching_sdists)}")
    return matching_wheels[0], matching_sdists[0]


def _verify_sdist(path: pathlib.Path) -> int:
    with tarfile.open(path, "r:gz") as archive:
        names = archive.getnames()
    missing = [
        rel
        for rel in SDIST_REQUIRED_FILES
        if not any(name.endswith("/" + rel) for name in names)
    ]
    if missing:
        print(f"FAIL: sdist missing release files: {', '.join(missing)}")
        return 1
    generated = [
        name
        for name in names
        if "__pycache__" in pathlib.PurePosixPath(name.replace("\\", "/")).parts
        or ".pyc" in pathlib.PurePosixPath(name.replace("\\", "/")).name
        or name.endswith(".pyo")
    ]
    if generated:
        print(f"FAIL: sdist contains generated Python cache files: {', '.join(generated[:5])}")
        return 1
    return 0


def _verify_wheel_contents(path: pathlib.Path) -> int:
    forbidden = {"yinyo/AGENTS.md", "yinyo/SOUL.md"}
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
    leaked = sorted(forbidden & names)
    if leaked:
        print(f"FAIL: wheel contains internal package docs: {', '.join(leaked)}")
        return 1
    return 0


def _run(*args, **kwargs) -> subprocess.CompletedProcess:
    kwargs.setdefault("timeout", SUBPROCESS_TIMEOUT_SECONDS)
    return subprocess.run(*args, **kwargs)


def _venv_python(venv: pathlib.Path) -> pathlib.Path:
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _write_incomplete_runtime_evidence(workspace: pathlib.Path) -> None:
    """Write non-live fixture data for installed CLI behavior checks."""

    workspace.mkdir(parents=True, exist_ok=True)
    _write_jsonl(
        workspace / "runtime.jsonl",
        [
            {"event": "service_start", "correlation_id": "service", "profile": "local", "transport": "http"},
            {"event": "service_stop", "correlation_id": "service", "status": "stopped", "transport": "http"},
            {"event": "webhook_url_verification", "correlation_id": "evt_url", "event_key": "evt_url"},
            {"event": "outbox_delivery", "correlation_id": "evt_text", "success": True},
            {"event": "outbox_delivery", "correlation_id": "evt_image", "success": True},
            {"event": "outbox_delivery", "correlation_id": "evt_card", "success": True, "fallback": True},
            {"event": "webhook_duplicate", "correlation_id": "evt_dup", "event_key": "evt_dup"},
        ],
    )
    _write_jsonl(
        workspace / "runtime_jobs.jsonl",
        [{"id": "job-wheel", "kind": "feishu_message", "status": "succeeded"}],
    )
    _write_jsonl(
        workspace / "gateway_events.jsonl",
        [
            {"event_key": "evt_url", "first_seen_at": 1.0},
            {"event_key": "evt_text", "first_seen_at": 1.0},
            {"event_key": "evt_image", "first_seen_at": 1.0},
            {"event_key": "evt_card", "first_seen_at": 1.0},
            {"event_key": "evt_dup", "first_seen_at": 1.0},
        ],
    )
    smoke_records = [
        {"scenario": "url_verification", "status": "passed", "live": False, "event_key": "evt_url"},
        {"scenario": "text_message_reply", "status": "passed", "live": False, "event_key": "evt_text"},
    ]
    _write_jsonl(workspace / "smoke_evidence.jsonl", smoke_records)


def _write_jsonl(path: pathlib.Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
