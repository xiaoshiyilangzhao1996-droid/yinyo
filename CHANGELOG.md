# Changelog

All notable changes to YINYO are documented here.

---

## 1.0.0-lite

- Promoted the public lite release line for GitHub users to install, configure,
  and validate against real Feishu apps.
- Kept full `1.0.0` blocked behind verified ws live smoke bundle and advanced
  live evidence.
- Documented the product/package version mapping: tag `v1.0.0-lite`, product
  version `1.0.0-lite`, Python package version `1.0.0rc1`.
- Local validation: 355 tests passing.

## 0.1.0-alpha.1

- Added release matrix, 15-case versioned harness corpus, smoke evidence gates, wheel verification, and 1.0 candidate guard.
- Added workspace-boundary corpus proof for read, search, write, and run-workdir containment.
- Added TemporalTree state recovery proof with provenance, stale-state, audit-trail, and disk-reload checks.
- Added trace-native failure diagnosis, adaptive-simplification proof ablation, and strengthened handoff replay with budget state plus trace history inheritance.
- Added external Feishu tester guide for GitHub users to install, run live smoke, build a redacted bundle, and report evidence without secrets.
- `1.0.0` remains blocked until verified Feishu live smoke and advanced live evidence exist.
