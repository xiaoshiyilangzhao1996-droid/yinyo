"""Prepare GitHub Release notes and asset checksums for a YINYO release."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "release-artifacts" / "v1.0.0-lite"


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare YINYO GitHub Release artifacts")
    parser.add_argument("--version", default="v1.0.0-lite", help="Git tag to prepare")
    parser.add_argument("--package-version", default="", help="Expected Python package version; defaults to pyproject")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output directory for generated release files")
    args = parser.parse_args()

    version = args.version.strip()
    package_version = (args.package_version or _package_version()).strip()
    output = pathlib.Path(args.output)
    notes = ROOT / "RELEASE_NOTES.md"
    blockers = []

    if not notes.is_file():
        blockers.append("RELEASE_NOTES.md missing")
    tag_commit = _git(["rev-parse", "--verify", f"{version}^{{commit}}"])
    head_commit = _git(["rev-parse", "HEAD"])
    if tag_commit.returncode != 0:
        blockers.append(f"tag not found: {version}")
    elif tag_commit.stdout.strip() != head_commit.stdout.strip():
        blockers.append(f"tag {version} does not point at HEAD")
    if _git(["diff", "--quiet"]).returncode != 0 or _git(["diff", "--cached", "--quiet"]).returncode != 0:
        blockers.append("working tree is not clean")

    assets = _release_assets(ROOT / "dist", package_version)
    if isinstance(assets, str):
        blockers.append(assets)
        assets_list: list[pathlib.Path] = []
    else:
        assets_list = assets

    if blockers:
        for blocker in blockers:
            print(f"FAIL: {blocker}", file=sys.stderr)
        return 1

    output.mkdir(parents=True, exist_ok=True)
    body = notes.read_text(encoding="utf-8")
    manifest = {
        "schema": "yinyo.github_release.v1",
        "version": version,
        "package_version": package_version,
        "commit": head_commit.stdout.strip(),
        "body": "RELEASE_BODY.md",
        "assets": [
            {
                "name": path.name,
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
            }
            for path in assets_list
        ],
    }
    (output / "RELEASE_BODY.md").write_text(body, encoding="utf-8")
    (output / "release-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    checksums = "\n".join(f"{item['sha256']}  {item['name']}" for item in manifest["assets"]) + "\n"
    (output / "SHA256SUMS.txt").write_text(checksums, encoding="utf-8")
    print(f"Prepared GitHub Release files in {output}")
    print(f"Release body: {output / 'RELEASE_BODY.md'}")
    print(f"Manifest: {output / 'release-manifest.json'}")
    print(f"Checksums: {output / 'SHA256SUMS.txt'}")
    return 0


def _package_version() -> str:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for line in pyproject.splitlines():
        if line.startswith("version = "):
            return line.split('"', 2)[1]
    raise RuntimeError("pyproject version missing")


def _release_assets(dist: pathlib.Path, package_version: str) -> list[pathlib.Path] | str:
    expected = {
        f"yinyo_agent-{package_version}-py3-none-any.whl",
        f"yinyo_agent-{package_version}.tar.gz",
    }
    assets = sorted(dist.glob("yinyo_agent-*"))
    names = {path.name for path in assets}
    missing = sorted(expected - names)
    stale = sorted(name for name in names if name not in expected)
    if missing:
        return "missing release assets: " + ", ".join(missing)
    if stale:
        return "unexpected release assets in dist: " + ", ".join(stale)
    return [dist / name for name in sorted(expected)]


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=False)


if __name__ == "__main__":
    raise SystemExit(main())
