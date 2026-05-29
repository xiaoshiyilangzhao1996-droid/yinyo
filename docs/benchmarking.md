<div align="center">

# Benchmarking

"Comparable dimensions, explicit limits."

![Scope](https://img.shields.io/badge/scope-benchmark-blue)
![Mode](https://img.shields.io/badge/mode-methodology-f59e0b)

</div>

YINYO is benchmarked against Hermes and OpenClaw as a product-design reference:
it borrows the expectation that a harness Agent should expose tools, memory,
runtime boundaries, verification, and operational evidence. YINYO does not claim to be more mature or more stable than those projects.

[Comparison](#comparison) · [Current Result](#current-result) · [Boundary](#boundary)

---

## Comparison

| Dimension | YINYO `v1.0.0-lite` standard |
|---|---|
| Product scope | Feishu + DeepSeek first, no broad platform sprawl. |
| Tooling | Small built-in tool surface with confirmation, evidence, and workspace boundaries. |
| Memory | TemporalTree facts, supersession, durability filtering, and recovery diagnostics. |
| Runtime | Feishu long connection by default, HTTP fallback, ACK boundary, idempotency, jobs, outbox, diagnostics. |
| Evolution | Trace2Skill requires failure trace, regression fixture, replay, promotion record, and post-promotion evidence. |
| Verification | Local scenario matrix, proof envelopes, proof ablation, release verifier, wheel verifier, public-tree verifier. |
| Governance | Secret scan, redacted bundles, release metadata gate, and explicit full `1.0.0` blockers. |

---

## Current Result

Local evidence is strong enough for a public lite release and real external
testing. It is not enough for stable `1.0.0`.

The current local acceptance line is:

```bash
python scripts/replay_scenarios.py --matrix
python scripts/verify_release.py --target 1.0.0-lite --candidate 1.0.0-lite --json
python scripts/verify_public_tree.py
python scripts/verify_secrets.py
python -m pytest tests -q
```

Full `1.0.0` requires the same framework claims to survive a verified live
Feishu ws bundle. That is the point where YINYO's product boundary becomes
externally proven rather than locally simulated.

---

## Boundary

YINYO's benchmark claim means:

- product dimensions were chosen with Hermes/OpenClaw-style harness expectations
  in mind;
- every public claim must be tied to source, tests, replay, or live evidence;
- missing maturity is stated as a boundary, not hidden behind broad marketing.

It does not mean:

- YINYO has broader integrations than Hermes or OpenClaw;
- YINYO has more production history;
- local fixtures can replace real Feishu live evidence.
