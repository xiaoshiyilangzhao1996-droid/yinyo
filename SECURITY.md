# YINYO Security Policy

## Reporting

Report vulnerabilities privately through
[GitHub Security Advisories](https://github.com/xiaoshiyilangzhao1996-droid/yinyo/security/advisories/new).

A useful report includes:

- Concise description and severity assessment.
- Affected component with file path and line range.
- Environment details, including Python version, OS, and model provider.
- Reproduction steps against the latest release.
- The trust boundary that was crossed.

---

## Trust Model

YINYO is a single-tenant personal agent. It runs on the deployer's own
infrastructure and operates inside that deployer's trust envelope.

The operating system is the only hard security boundary. The governance policy,
verification gate, and tool allowlist reduce accidental damage, but they are not
containment against an adversarial process or compromised host.

---

## Attack Surfaces

| Surface | Risk | Mitigation |
|---|---|---|
| LLM-emitted shell commands | High: a model may emit destructive commands. | Governance policy blocks risky patterns and records blocked steps. |
| Feishu prompt injection | Medium: hostile text may arrive from chats. | Session isolation, explicit tool permissions, and evidence records. |
| Local memory files | Low: filesystem access already compromises the agent. | Treat `MEMORY.md` as data, not executable code. |
| API key leakage | Critical. | Keep keys out of git, memory, docs, and shared logs. Use local env/config only. |
| Live smoke bundles | Medium: evidence can include operational metadata. | Share only redacted bundles created by `yinyo smoke bundle`. |

---

## Governance Policy

`yinyo/governance.py` provides a heuristic risk policy:

- Commands matching dangerous patterns are blocked.
- Blocked steps are tracked in run manifests.
- Consecutive failures can escalate thinking mode.

This policy prevents common mistakes. It is not a sandbox and must not be
documented as one.

---

## Supported Versions

| Version | Supported |
|---|---|
| `0.1.x-alpha` | Active alpha |
| Internal `vX.Y` prototypes | Not public release lines |
| `< 0.1.0` | End of life |

---

## Deployer Rules

1. Do not expose YINYO to untrusted multi-user channels without an OS or
   container boundary appropriate for the risk.
2. Use dedicated Feishu and model-provider keys with the minimum required
   permissions.
3. Validate config with `yinyo serve --dry-run` and confirm secrets are
   redacted.
4. Keep raw `.env`, runtime JSONL, and live smoke evidence out of git.
5. Run `python scripts/verify_secrets.py` before sharing logs, bundles, wheels,
   or release artifacts.
6. Review `MEMORY.md` and runtime logs periodically; frequent blocked steps
   require investigation.
7. Use [docs/incident-playbook.md](docs/incident-playbook.md) for security
   incidents.

---

## Release Boundary

Local release-matrix, replay, diagnostic, or fixture evidence does not replace
live Feishu evidence for `1.0.0`. It proves harness code paths only.

The primary `1.0.0` release path is a verified redacted `transport=ws` smoke
bundle with matching `service_start`, `ws_transport_start`, and
`ws_event_received` runtime evidence. HTTP evidence is fallback coverage only.
Matching `ws_sdk_session_id` markers are redacted provenance markers, not
secrets; the bundle verifier checks that manifest `live_provenance` matches the
latest runtime log markers before accepting the bundle.

Advanced live evidence must be recorded through `yinyo smoke record-advanced`.
Operators must not hand-edit `smoke_evidence.jsonl` or advanced records.
Hand-edited advanced JSONL records do not satisfy the 1.0 release gate.
Advanced records include a `yinyo.advanced_live_proof.v1` digest over redacted
required fields; missing or mismatched proof digests are release blockers.

Do not bypass the release verifier, hand-edit live smoke records, or publish raw
evidence files to satisfy a release gate. Raw `.env`, `runtime.jsonl`,
`runtime_jobs.jsonl`, `gateway_events.jsonl`, and `smoke_evidence.jsonl` are
local evidence only and must not be published or shared as release artifacts.
Publish or share only verified redacted bundles created by `yinyo smoke bundle`;
do not share raw runtime logs, raw job stores, raw event stores, or raw smoke
evidence files.

---

## Acknowledgments

This policy is modeled after the
[Hermes Agent Security Policy](https://github.com/NousResearch/hermes-agent/blob/main/SECURITY.md).
