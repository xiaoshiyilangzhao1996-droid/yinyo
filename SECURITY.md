# YINYO Security Policy

## Reporting a Vulnerability

Report privately via [GitHub Security Advisories](https://github.com/xiaoshiyilangzhao1996-droid/yinyo/security/advisories/new).

A useful report includes:
- Concise description and severity assessment.
- Affected component with file path and line range.
- Environment details (Python version, OS, DeepSeek model version).
- Reproduction steps against the latest release.
- Which trust boundary is crossed (see §2).

---

## Trust Model

YINYO is a **single-tenant personal agent**. It runs on the user's own infrastructure and operates within the user's trust envelope.

### Security Boundary

The only security boundary is the **operating system**. Nothing inside the agent process constitutes containment — not the governance policy engine, not the verification gate, not the tool allowlist.

### Attack Surfaces

| Surface | Risk | Mitigation |
|---------|------|-----------|
| **LLM-emitted shell commands** | High — model may emit destructive commands | Governance policy blocks risky patterns; verification gate requires hash match |
| **Prompt injection via Feishu** | Medium — malicious users in group chats | Session isolation per user/chat; governance policy per session |
| **Memory file manipulation** | Low — if attacker has filesystem access, agent is compromised anyway | MEMORY.md is plain text; no executable content |
| **API key leakage** | Critical | Never store keys in MEMORY.md. Use environment variables only. |

### Governance Policy

The `governance.py` module provides a risk policy engine:
- Commands matching dangerous patterns are blocked.
- Blocked steps are tracked and reported in run manifests.
- Consecutive failures escalate thinking mode (THINK_HIGH → THINK_MAX).

**This is a heuristic, not a security boundary.** It prevents accidents but does not protect against a determined adversarial LLM.

---

## Supported Versions

| Version | Supported |
|---------|-----------|
| v7.0 | ✅ Active |
| v6.0 | ✅ Security fixes |
| v5.0 | ✅ Security fixes |
| < v5.0 | ❌ End of life |

---

## Best Practices for Deployers

1. **Never expose YINYO to untrusted multi-user channels** without OS-level sandboxing.
2. **Use a dedicated API key** with minimal permissions.
3. **Run in a container or sandbox** for production deployments.
4. **Review MEMORY.md periodically** — it accumulates from LLM-generated reflections.
5. **Monitor blocked steps** — frequent blocks indicate either a problem with the agent or malicious input.

---

## Acknowledgments

This security policy is modeled after the [Hermes Agent Security Policy](https://github.com/NousResearch/hermes-agent/blob/main/SECURITY.md).
