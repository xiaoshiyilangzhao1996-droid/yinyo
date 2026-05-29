# AGENTS.md - YINYO Agent Rules

These rules are executable working constraints for future agents in this repo.

## Project Home

- Work from the checked-out repository root, not from dated session directories,
  exported chat logs, build outputs, or live smoke workspaces.
- YINYO is a harness Agent product benchmarked against Hermes and OpenClaw.
  Feishu is the current product surface and release-evidence path, not a
  generic bot-wrapper scope.

## How To Read

1. Start with `README.md` for product scope, current version, and release status.
2. Read `docs/handoff.md` for cross-session context, product decisions, and the
   current local/live evidence boundary.
3. Read `docs/spec.md` before changing product behavior or release gates.
4. Read `docs/deployment.md` and `MAINTENANCE.md` before touching runtime, smoke, or release workflow code.
5. Read `SECURITY.md` before handling logs, config, tokens, evidence bundles, or Feishu payloads.

## How To Answer

- Lead with verified facts, not memory or intent.
- When a release claim depends on a command, run the command and report the result.
- If a claim depends on live Feishu evidence and the evidence is missing, say it is missing.
- Keep user-facing status concise, but include blockers that affect `1.0.0`.

## Hard Rules

- Do not call YINYO `1.0.0` ready unless `python scripts/verify_release.py --target 1.0.0 --candidate 1.0.0` passes with real live Feishu evidence or a verified redacted bundle.
- Do not fake live Feishu smoke records. Live evidence must come from real callbacks and the supported smoke/advanced recorder flow.
- Do not hand-edit `smoke_evidence.jsonl` to satisfy advanced scenarios; use `yinyo smoke record-advanced`.
- Do not commit raw `.env` files, unredacted runtime logs, live smoke JSONL, or local `workspace/` runtime state.
- Keep public versions SemVer-based. Historical `v8.x` labels are internal prototype history only.
- Prefer small, test-backed changes over broad rewrites.

## Common Links

- Runtime entry: `yinyo/service.py`
- Feishu long connection: `yinyo/feishu_ws.py`
- HTTP fallback: `yinyo/feishu_adapter.py`
- Smoke evidence: `yinyo/smoke.py`
- Release audit: `yinyo/readiness.py` and `scripts/verify_release.py`
- Installed-wheel gate: `scripts/verify_wheel.py`
- Scenario matrix: `scripts/replay_scenarios.py` and `examples/feishu_scenarios.json`
- Cross-session handoff: `docs/handoff.md`

## Risk Points

- The default release blocker is missing real Feishu long-connection and advanced live evidence.
- Local scenario replay proves product paths, but it does not replace live platform evidence.
- Local JSONL stores are single-writer; respect `runtime_lock_path` and do not delete foreign or unparseable locks.
- Service shutdown logs must avoid secret-bearing exception messages; use `error_type` only.
- Bundle verification must recompute hashes and `bundle_digest`; do not trust manifest text alone.
