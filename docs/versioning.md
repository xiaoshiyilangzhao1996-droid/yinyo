# Versioning Policy

YINYO separates external product versions from internal engineering stages.

---

## External Version

The public package and release line follows SemVer:

```text
MAJOR.MINOR.PATCH[-PRERELEASE]
```

Python package metadata uses the equivalent PEP 440 spelling. For example,
`1.0.0-lite` is published as `1.0.0rc1` for Python packaging because PEP 440
does not accept the literal `lite` suffix in package metadata.

Current external version:

| Surface | Value |
|---------|-------|
| Product version | `1.0.0-lite` |
| Python package version | `1.0.0rc1` |
| Release maturity | Lite |

`1.0.0-lite` is the first externally downloadable GitHub product line for real
Feishu validation. Full `1.0.0` remains reserved for the first stable release
with verified live smoke evidence.

---

## Internal Stage

Internal stages describe acceptance depth. They are not release versions.

| Stage | Meaning |
|-------|---------|
| P0 | Local agent loop is real, bounded, evidence-backed, and importable. |
| P1 | Product loop is testable: Feishu adapter, memory evolution, reflection, fallback, and manifests. |
| P2 | Evolution loop is constrained by regression fixtures, blind-test records, and context-retention reports. |

Internal prototype labels such as `v8.x` are historical build milestones. They
must not be used as package versions, README release versions, or public tags.

---

## Release Map

| External version | Maturity | Required evidence |
|------------------|----------|-------------------|
| `0.1.0-alpha.1` | Alpha | Unit tests green, spec updated, versioning policy in place. |
| `1.0.0-lite` | Lite | Local release gates green, GitHub tester guide, clean public file surface, full `1.0.0` gate explicitly blocked by live evidence. |
| `0.2.0-alpha.1` | Alpha | Fresh install, external tester guide, live Feishu smoke test, redacted evidence bundle. |
| `0.3.0-beta.1` | Beta | CI, security review, release notes, rollback path, documented limitations. |
| `1.0.0` | Stable | Stable install, supported configuration, verified core workflows, no undocumented critical path. |

---

## Rules

- `pyproject.toml` and `yinyo.__version__` are the source of truth for the
  current external package version.
- README files describe product maturity and current release status, not every
  internal engineering milestone.
- `CHANGELOG.md` records external releases first. Internal prototype history may
  be preserved under a clearly marked historical section.
- Internal gates live in `docs/spec.md`. New product claims require new
  acceptance checks before they appear as completed capabilities.
- Never claim a blind-test pass rate, live platform readiness, or public-release
  maturity unless the repo contains reproducible evidence.
- `v1.0.0` must not be tagged until `python scripts/verify_release.py --target 1.0.0 --bundle <dir> --candidate 1.0.0` passes against verified live smoke evidence or a verified redacted evidence bundle.
- `1.0.0` metadata promotion must use `python scripts/prepare_release_metadata.py --version 1.0.0 --verified-bundle <dir>` first as a dry run, then the same command with `--apply`. The apply path refuses unverified bundles.
- `v1.0.0-lite` may be tagged when `python scripts/verify_release.py --target 1.0.0-lite --candidate 1.0.0-lite` passes. It must remain visibly distinct from full `v1.0.0`.
- `v1.0.0-lite` GitHub Release notes should use `RELEASE_NOTES.md` and attach
  only the `1.0.0rc1` wheel and sdist from `dist/`.
- GitHub source releases should contain only the product-facing tree:
  README, license/security/contribution docs, package source, tests, scripts,
  docs, examples, corpus, and CI. Generated runtime data, local workspaces,
  build outputs, virtual environments, caches, and raw env files must stay out
  of git and package artifacts; `python scripts/verify_public_tree.py` enforces
  this boundary.
- External testers may run and report the lite or release-candidate line before
  `1.0.0`, but release notes and README status must keep that line clearly
  labeled as non-stable until the candidate guard passes.
