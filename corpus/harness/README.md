<div align="center">

# Harness Corpus

"Versioned local harness inputs and oracles."

![Schema](https://img.shields.io/badge/schema-v1-2ea043)
![Scope](https://img.shields.io/badge/scope-local%20harness-blue)

</div>

This corpus holds versioned parameters and expectations for local YINYO harness
scenarios. It does not replace live Feishu evidence for `1.0.0`.

[Format](#format) · [Boundary](#boundary)

---

## Format

`scenarios.v1.json` contains cases with `id`, `runner`, `inputs`, `expect`,
`proof_required`, and proof-envelope requirements. Python runners still execute
the behavior; the corpus supplies the acceptance oracle.

---

## Boundary

Local corpus replay proves harness mechanisms: context retention, memory policy,
release gate behavior, and similar offline checks. Public `1.0.0` still requires
a verified redacted Feishu ws bundle and advanced live smoke records.
