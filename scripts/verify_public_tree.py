"""Verify that the GitHub-facing repository tree stays product-clean."""

from __future__ import annotations

import pathlib
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]

ALLOWED_ROOT_FILES = {
    ".gitignore",
    "AGENTS.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "MAINTENANCE.md",
    "MANIFEST.in",
    "README.md",
    "README.zh-CN.md",
    "RELEASE_NOTES.md",
    "SECURITY.md",
    "pyproject.toml",
    "yinyo.env.example",
}

ALLOWED_ROOT_DIRS = {
    ".github",
    "corpus",
    "docs",
    "examples",
    "scripts",
    "tests",
    "yinyo",
}

FORBIDDEN_TRACKED_PARTS = {
    ".venv",
    ".pytest_cache",
    "__pycache__",
    "build",
    "dist",
    "release-artifacts",
    "temp",
    "workspace",
    "yinyo_agent.egg-info",
}

FORBIDDEN_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".egg",
    ".db",
}

FORBIDDEN_NAMES = {
    ".env",
    "yinyo.env",
    "runtime.jsonl",
    "runtime_jobs.jsonl",
    "gateway_events.jsonl",
    "smoke_evidence.jsonl",
}


def main() -> int:
    paths = _git_paths()
    blockers = []
    for rel in paths:
        path = pathlib.PurePosixPath(rel.replace("\\", "/"))
        root = path.parts[0] if path.parts else ""
        if len(path.parts) == 1:
            if root not in ALLOWED_ROOT_FILES and root not in ALLOWED_ROOT_DIRS:
                blockers.append(f"unexpected root entry: {rel}")
        elif root not in ALLOWED_ROOT_DIRS:
            blockers.append(f"unexpected root directory: {root}")
        if any(part in FORBIDDEN_TRACKED_PARTS for part in path.parts):
            blockers.append(f"forbidden generated path: {rel}")
        if path.name in FORBIDDEN_NAMES:
            blockers.append(f"forbidden secret/runtime file: {rel}")
        if path.suffix in FORBIDDEN_SUFFIXES:
            blockers.append(f"forbidden generated suffix: {rel}")
        if path.name.endswith((".runtime.jsonl", ".runtime_jobs.jsonl", ".gateway_events.jsonl", ".smoke_evidence.jsonl")):
            blockers.append(f"forbidden runtime evidence file: {rel}")

    if blockers:
        for blocker in sorted(set(blockers)):
            print(f"FAIL: {blocker}")
        return 1
    print(f"Public tree verification passed: {len(paths)} tracked path(s)")
    return 0


def _git_paths() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        print(result.stderr.strip(), file=sys.stderr)
        raise SystemExit(result.returncode)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


if __name__ == "__main__":
    raise SystemExit(main())
