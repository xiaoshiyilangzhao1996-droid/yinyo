# AGENTS.md - YINYO Package Rules

These package-level rules apply to code under `yinyo/`.

## How To Read

1. Start with the nearest module tests in `tests/`.
2. For runtime and smoke changes, read `yinyo/config.py`, `yinyo/service.py`, `yinyo/smoke.py`, and `yinyo/readiness.py` together.
3. For Feishu changes, keep `yinyo/feishu_ws.py`, `yinyo/feishu_adapter.py`, `yinyo/gateway.py`, and `yinyo/outbox.py` aligned.

## How To Answer

- Name the files changed and the verification commands run.
- Separate local evidence from live Feishu evidence.
- Treat missing live evidence as a release blocker, not a documentation detail.

## Hard Rules

- Do not bypass token verification, idempotency checks, ACK deadline tracking, job persistence, or outbox delivery evidence.
- Do not log secret values or raw exception text from service failures.
- Do not weaken `verify_full_smoke_evidence`, `verify_advanced_live_evidence`, or bundle digest verification to make `1.0.0` pass.
- Keep HTTP webhook behavior tested, but preserve long connection as the primary `1.0.0` proof path.
- Add focused tests when touching shared runtime, release-gate, or evidence logic.

## Common Links

- Config validation: `config.py`
- Service lifecycle: `service.py`
- Release readiness: `readiness.py`
- Smoke records and bundles: `smoke.py`
- Diagnostics: `diagnostics.py`
- Runtime locks: `runtime_lock.py`

## Risk Points

- `smoke_mode=true` is only for controlled release smoke and must be rejected for production profiles.
- Stale same-host locks may be recovered only when the recorded PID no longer exists.
- Advanced live records require the controlled recorder marker.
- Candidate `1.0.0` requires verified live evidence or a verified bundle; HTTP-only evidence is not the primary release proof.
