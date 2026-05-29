"""Prepare external release metadata after the final 1.0 evidence gate passes."""

from __future__ import annotations

import argparse
import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yinyo.smoke import verify_smoke_evidence_bundle

CURRENT_PRODUCT_VERSION = "1.0.0-lite"
CURRENT_PACKAGE_VERSION = "1.0.0rc1"


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare YINYO release metadata")
    parser.add_argument("--version", required=True, help="External product version, for example 1.0.0")
    parser.add_argument("--package-version", default="", help="PEP 440 package version; defaults to --version")
    parser.add_argument("--verified-bundle", default="", help="Required with --apply for 1.0.0; redacted live smoke bundle that already verifies")
    parser.add_argument("--apply", action="store_true", help="Write files. Omit for a dry run.")
    args = parser.parse_args()

    product_version = args.version.strip()
    package_version = (args.package_version or product_version).strip()
    if not _valid_version(product_version):
        print(f"FAIL: unsupported product version: {product_version}", file=sys.stderr)
        return 2
    if not _valid_version(package_version):
        print(f"FAIL: unsupported package version: {package_version}", file=sys.stderr)
        return 2

    bundle = _verified_release_bundle(args.verified_bundle, require=args.apply and product_version == "1.0.0")
    if bundle is False:
        return 2 if args.apply and product_version == "1.0.0" and not args.verified_bundle else 1

    replacements = _release_replacements(product_version, package_version)
    if args.apply:
        for rel, text in replacements.items():
            (ROOT / rel).write_text(text, encoding="utf-8")
        if isinstance(bundle, dict):
            print(f"Release metadata updated for {product_version} ({package_version}) from verified bundle {args.verified_bundle}")
        else:
            print(f"Release metadata updated for {product_version} ({package_version})")
    else:
        print(f"Dry run: release metadata would update {len(replacements)} file(s) for {product_version} ({package_version})")
        if isinstance(bundle, dict):
            print(f"Verified bundle: {args.verified_bundle}")
        for rel in replacements:
            print(f"- {rel}")
    return 0


def _verified_release_bundle(path: str, *, require: bool) -> dict[str, object] | bool | None:
    if not path:
        if require:
            print("FAIL: --apply for 1.0.0 requires --verified-bundle <bundle-dir>", file=sys.stderr)
            return False
        return None
    bundle = verify_smoke_evidence_bundle(path, require_run_handoff=True)
    if not bundle.get("ok"):
        print("FAIL: verified bundle check failed: " + ", ".join(bundle.get("blockers", [])), file=sys.stderr)
        return False
    if bundle.get("manifest", {}).get("runtime", {}).get("transport") != "ws":
        print("FAIL: 1.0.0 release metadata requires a verified ws long-connection bundle", file=sys.stderr)
        return False
    return bundle


def _valid_version(value: str) -> bool:
    return bool(re.fullmatch(r"\d+\.\d+\.\d+(?:[-a-zA-Z0-9.]+)?", value))


def _release_replacements(product_version: str, package_version: str) -> dict[str, str]:
    files = {
        "pyproject.toml": _replace_required(
            _read("pyproject.toml"),
            f'version = "{CURRENT_PACKAGE_VERSION}"',
            f'version = "{package_version}"',
        ),
        "yinyo/__init__.py": _replace_required(
            _replace_required(
                _read("yinyo/__init__.py"),
                f"YINYO {CURRENT_PRODUCT_VERSION}",
                f"YINYO {product_version}",
            ),
            f'__version__ = "{CURRENT_PACKAGE_VERSION}"',
            f'__version__ = "{package_version}"',
        ),
        "README.md": _replace_readme_versions(_read("README.md"), product_version, package_version),
        "README.zh-CN.md": _replace_readme_versions(_read("README.zh-CN.md"), product_version, package_version),
        "docs/versioning.md": _replace_versioning(_read("docs/versioning.md"), product_version, package_version),
        "CHANGELOG.md": _replace_changelog(_read("CHANGELOG.md"), product_version),
        "MAINTENANCE.md": _replace_required(
            _read("MAINTENANCE.md"),
            f"release-{CURRENT_PACKAGE_VERSION}-2ea043",
            f"release-{package_version}-2ea043",
        ),
    }
    return files


def _replace_readme_versions(text: str, product_version: str, package_version: str) -> str:
    text = _replace_required(
        text,
        f"version-{CURRENT_PRODUCT_VERSION.replace('-', '--')}-2ea043",
        f"version-{product_version.replace('-', '--')}-2ea043",
    )
    text = _replace_required(text, f"`{CURRENT_PRODUCT_VERSION}`", f"`{product_version}`")
    return _replace_required(text, f"`{CURRENT_PACKAGE_VERSION}`", f"`{package_version}`")


def _replace_versioning(text: str, product_version: str, package_version: str) -> str:
    text = _replace_required(text, f"| Product version | `{CURRENT_PRODUCT_VERSION}` |", f"| Product version | `{product_version}` |")
    text = _replace_required(text, f"| Python package version | `{CURRENT_PACKAGE_VERSION}` |", f"| Python package version | `{package_version}` |")
    return _replace_required(text, "| Release maturity | Lite |", "| Release maturity | Stable |")


def _replace_changelog(text: str, product_version: str) -> str:
    if f"## {product_version}" in text:
        return text
    heading = (
        f"## {product_version}\n\n"
        "- Promoted external release metadata after the verified 1.0 evidence gate.\n\n"
    )
    marker = f"## {CURRENT_PRODUCT_VERSION}"
    if marker not in text:
        raise RuntimeError(f"CHANGELOG.md missing expected heading: {marker}")
    return text.replace(marker, heading + marker, 1)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _replace_required(text: str, old: str, new: str) -> str:
    if old not in text:
        raise RuntimeError(f"expected text not found: {old}")
    return text.replace(old, new)


if __name__ == "__main__":
    raise SystemExit(main())
