"""Scan repository text files for committed secrets."""

from __future__ import annotations

import argparse
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yinyo.governance import scan_secrets


SKIP_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "htmlcov",
    "workspace",
    "yinyo_agent.egg-info",
}

TEXT_SUFFIXES = {
    ".cfg",
    ".example",
    ".in",
    ".ini",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}

ALLOW_SUBSTRINGS = {
    "api_key=api_key",
    "api_key=config.deepseek_api_key",
    "api_key=config.deepseek_api_ke",
    "api_key=deepseek_key",
    "api_key=provider[",
    "api_key = os.environ.get(",
    "api_key=\"sk-key\"",
    "api_key=\"test-key\"",
    'api_key": "DEEPSEEK_API_KEY"',
    "secret = app_secret",
    "secret = self.config.get(",
    "secret=config.app_secret",
    "secret=self.app_secret",
    'secret": "FEISHU_APP_SECRET"',
    "super-secret",
    "token = event.get(",
    "token = self._get_tenant_token",
    "token = self.config.get(",
    "token = verify_token",
    'token": "FEISHU_VERIFY_TOKEN"',
    'token": "good-token"',
    "token:",
    "token=\"good-token\"",
    "token=self.verify_token",
    "verify-secret",
    "secret-token",
    "sk-secret",
    "sk-test",
    "sk-xxx",
    "sk-projABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "sk-projABCDEFGHIJKLMNOPQRSTUVW",
    "sk-proj-abcdefghijklmnopqrstuvwxyz",
    "qwerty12345678",
    "abcdefghijklmnopqrstuvwxyz123456",
    "eyJhbGciOiJIUzI1NiJ9.abcdefghijklmnop",
    "Bearer eyJhbGciOiJIUzI1NiJ9.ab",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify no real secrets are committed")
    parser.add_argument("--root", default=str(ROOT), help="Repository root to scan")
    args = parser.parse_args()

    root = pathlib.Path(args.root).resolve()
    findings = []
    for path in _iter_text_files(root):
        rel = path.relative_to(root).as_posix()
        text = _read_text(path)
        if text is None:
            continue
        for hit in scan_secrets(text):
            match = hit.get("match", "")
            if _is_allowed(rel, match):
                continue
            findings.append({"path": rel, "match": match, "pattern": hit.get("pattern", "")})

    if findings:
        for item in findings:
            print(f"FAIL: possible secret in {item['path']}: {item['match']}")
        return 1

    print("Secret scan passed")
    return 0


def _iter_text_files(root: pathlib.Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.resolve() == pathlib.Path(__file__).resolve():
            continue
        parts = set(path.relative_to(root).parts)
        if parts & SKIP_DIRS:
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        yield path


def _read_text(path: pathlib.Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def _is_allowed(rel: str, match: str) -> bool:
    if any(allowed in match or match in allowed for allowed in ALLOW_SUBSTRINGS):
        return True
    if rel.startswith("tests/") and ("secret" in match.lower() or "token" in match.lower() or "api_key" in match.lower()):
        return True
    if rel.startswith("docs/") and ("xxx" in match.lower() or "<" in match):
        return True
    return False


if __name__ == "__main__":
    raise SystemExit(main())
