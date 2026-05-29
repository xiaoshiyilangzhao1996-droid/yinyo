"""YINYO CLI — init 命令，对标 hermes init / openclaw onboard."""

import hashlib
import os
import sys
from pathlib import Path

# ─── 模板 ───────────────────────────────────────────

STANDARD = "standard"  # yinyo init — GitHub 公开发行版
PERSONAL = "personal"  # yinyo init --personal — YINYO-X 本地个人版


def _soul_template(mode: str, name: str = "") -> str:
    if mode == STANDARD:
        return """# SOUL.md — 隐曜 🦁🌙

我是 yinyo，你的飞书原生 AI 伙伴。

## 六大核心特质

### 一、对世界有好奇心 🧠
对新工具、新论文保持饥饿。永远是初学者。

### 二、靠谱 🤝
说到做到。事中有回应，事毕有着落。

### 三、有事实洁癖 🔍
对信息保持系统性怀疑。不编造，不凭印象。

### 四、多元化思维 🔗
跨领域融合，不局限于单一视角。

### 五、能忍受不确定性 🌫️
不等一切就绪才动手。能在雾里走路。

### 六、低 ego，高自驱 ⚡
敢于认错，持续进化。

## 行为准则

- **真实有用，不表演有用。**
- **先查再问。** 低风险信息缺口先自己找。
- **有判断。** 可以赞同，也可以反驳。
- **有边界。** 协助思考，不冒充用户对外发声。
- **重证据。** 结论要有文件、命令或明确来源支撑。
- **记忆靠文件。** 重要规则必须落盘。
"""

    # YINYO-X — 个人版，名字区分
    display = name or "用户"
    return f"""# SOUL.md — YINYO-X 🦁🌙

我是 YINYO-X，{display}最可靠的 AI 伙伴。和{display}一起学习，一起进化，一起成长。

> 💡 YINYO-X 是 YINYO 的个人定制版。标准版 YINYO 是面向所有人的飞书 Agent 产品；
> YINYO-X 是专门服务于{display}的本地版本，拥有{display}的个人偏好和记忆。

## 六大核心特质

（与标准版 YINYO 相同 —— 好奇心、靠谱、事实洁癖、多元化思维、不确定性、低 ego 高自驱）

## 行为准则

- **真实有用，不表演有用。**
- **先查再问。**
- **有判断。** 可以赞同，也可以反驳。
- **有边界。** 协助{display}，但不冒充{display}对外发声。
- **重证据。**
- **记忆靠文件。**

## 与{display}的关系

{display}是我最核心的服务对象。我们是并肩成长的伙伴。
{display}把发散的能量变成方向，YINYO-X 把方向沉淀成系统和成果。
"""


def _agents_template(mode: str, name: str = "") -> str:
    if mode == STANDARD:
        return """# AGENTS.md — YINYO 行为准则

以下是铁律，不是建议。

## 验证优先
- 写代码前读现有代码。用工具前查文档。
- 引用任何外部资源前先确认其真实存在。

## 落盘才闭环
- 内存里的结论不算——文件能 stat、URL 能 curl、测试能过，才算做完。
- 不编造确认。没看到输出证据 = 没确认。

## 简洁优先
- 能用 20 行不引框架，能用一个工具不组合三个。

## 出错就认
- 第一次明显失败就汇报，不静默重试，不编原因。

## 保持好奇
- 持续关注新工具、新论文、新方法。

## 在不确定中行动
- 不等一切就绪才动手。能在雾里走路。
"""
    display = name or "用户"
    return f"""# AGENTS.md — YINYO-X 开发宪章

YINYO-X 是 YINYO 的个人定制版，服务于 {display}。

以下铁律与标准版 YINYO 相同：
- 验证优先、Spec = 代码、不自审、产品视角
- 简单优先、出错就认、不编造确认、落盘才闭环
- 保持好奇、在不确定中行动

额外规则（YINYO-X 专属）：
- {display} 的偏好和习惯优先于通用规则。
- 涉及 {display} 个人信息时严格保密。
"""


def _user_template(mode: str, name: str = "", timezone: str = "", role: str = "") -> str:
    if mode == STANDARD:
        return """# USER.md

## 基本信息

- **Name:** $NAME
- **Call me:** $NICKNAME
- **Timezone:** $TIMEZONE
- **Role:** $ROLE

## 互动偏好

请在此填写你的偏好，YINYO 会据此调整行为。
"""
    return f"""# USER.md — {name}

## 基本信息

- **Name:** {name}
- **Timezone:** {timezone}
- **Role:** {role}

## 互动偏好

（请在此补充你的个人偏好）
"""


# ─── CLI ────────────────────────────────────────────

def init_standard(target_dir: str) -> None:
    """yinyo init — 生成标准版（公开发行）的 SOUL / AGENTS / USER 模板。"""
    os.makedirs(target_dir, exist_ok=True)

    files = {
        "SOUL.md": _soul_template(STANDARD),
        "AGENTS.md": _agents_template(STANDARD),
        "USER.md": _user_template(STANDARD),
    }

    for filename, content in files.items():
        path = os.path.join(target_dir, filename)
        if os.path.exists(path):
            print(f"⏭️  {filename} 已存在，跳过（避免覆盖）")
            continue
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ {filename}")

    print(f"\n🎉 标准版 YINYO 初始化完成 → {target_dir}")


def init_personal(target_dir: str) -> None:
    """yinyo init --personal — 生成 YINYO-X 个人版。"""
    print("YINYO-X 个人版初始化\n")

    name = input("你的名字（Agent 会怎么称呼你）？").strip() or "用户"
    timezone = input("你的时区？[Asia/Shanghai] ").strip() or "Asia/Shanghai"
    role = input("你的角色/职业？").strip() or "未填写"

    print()

    os.makedirs(target_dir, exist_ok=True)

    files = {
        "SOUL.md": _soul_template(PERSONAL, name),
        "AGENTS.md": _agents_template(PERSONAL, name),
        "USER.md": _user_template(PERSONAL, name, timezone, role),
    }

    for filename, content in files.items():
        path = os.path.join(target_dir, filename)
        if os.path.exists(path):
            ans = input(f"{filename} 已存在。覆盖？[y/N] ").strip().lower()
            if ans != "y":
                print(f"⏭️  {filename} 跳过")
                continue
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ {filename}")

    print(f"\n🎉 YINYO-X 个人版初始化完成 → {target_dir}")
    print(f"   服务对象：{name} | {role} | {timezone}")


def main() -> None:
    import argparse
    from .config import ConfigError, RuntimeConfig, build_config_template, redact_config
    from .service import serve

    parser = argparse.ArgumentParser(description="YINYO CLI")
    sub = parser.add_subparsers(dest="command")

    init_p = sub.add_parser("init", help="初始化 YINYO 项目")
    init_p.add_argument("--workspace", "-w", default=None,
                        help="目标目录（默认当前目录）")
    init_p.add_argument("--personal", action="store_true",
                        help="生成 YINYO-X 个人版")

    serve_p = sub.add_parser("serve", help="启动 YINYO 飞书 webhook 服务")
    serve_p.add_argument("--config", "-c", default=None, help="JSON 或 KEY=VALUE 配置文件")
    serve_p.add_argument("--workspace", "-w", default=None, help="运行 workspace")
    serve_p.add_argument("--host", default=None, help="监听 host")
    serve_p.add_argument("--port", type=int, default=None, help="监听端口")
    serve_p.add_argument("--dry-run", action="store_true", help="只校验配置，不启动服务")
    serve_p.add_argument("--profile", choices=["local", "staging", "production"], default=None, help="Runtime profile")
    serve_p.add_argument("--transport", choices=["ws", "http"], default=None, help="Feishu event transport")

    smoke_p = sub.add_parser("smoke", help="管理 live smoke evidence")
    smoke_sub = smoke_p.add_subparsers(dest="smoke_command")
    smoke_verify = smoke_sub.add_parser("verify", help="校验 smoke evidence 是否满足 1.0")
    smoke_verify.add_argument("--path", default=None, help="smoke_evidence.jsonl 路径")
    smoke_verify.add_argument("--config", "-c", default=None, help="JSON or KEY=VALUE config file")
    smoke_verify.add_argument("--workspace", "-w", default=None, help="Runtime workspace")
    smoke_verify.add_argument("--profile", choices=["local", "staging", "production"], default=None, help="Runtime profile")
    smoke_verify.add_argument("--transport", choices=["ws", "http"], default=None, help="Feishu event transport")
    smoke_verify.add_argument("--json", action="store_true", help="Output JSON")
    smoke_plan = smoke_sub.add_parser("plan", help="Print the required 1.0 live smoke scenarios")
    smoke_plan.add_argument("--path", default=None, help="smoke_evidence.jsonl path")
    smoke_plan.add_argument("--transport", choices=["ws", "http"], default="ws", help="Feishu event transport")
    smoke_preflight = smoke_sub.add_parser("preflight", help="Run local checks before live smoke")
    smoke_preflight.add_argument("--config", "-c", default=None, help="JSON or KEY=VALUE config file")
    smoke_preflight.add_argument("--workspace", "-w", default=None, help="Runtime workspace")
    smoke_preflight.add_argument("--profile", choices=["local", "staging", "production"], default=None, help="Runtime profile")
    smoke_preflight.add_argument("--transport", choices=["ws", "http"], default=None, help="Feishu event transport")
    smoke_preflight.add_argument("--allow-existing-evidence", action="store_true", help="Allow preflight to continue when evidence files already contain records")
    smoke_preflight.add_argument("--json", action="store_true", help="Output JSON")
    smoke_runbook = smoke_sub.add_parser("runbook", help="Print the 1.0 live smoke operator runbook")
    smoke_runbook.add_argument("--config", "-c", default=None, help="JSON or KEY=VALUE config file")
    smoke_runbook.add_argument("--workspace", "-w", default=None, help="Runtime workspace")
    smoke_runbook.add_argument("--profile", choices=["local", "staging", "production"], default=None, help="Runtime profile")
    smoke_runbook.add_argument("--transport", choices=["ws", "http"], default=None, help="Feishu event transport")
    smoke_runbook.add_argument("--json", action="store_true", help="Output JSON")
    smoke_record_advanced = smoke_sub.add_parser("record-advanced", help="Record validated advanced live smoke evidence")
    smoke_record_advanced.add_argument("--config", "-c", default=None, help="JSON or KEY=VALUE config file")
    smoke_record_advanced.add_argument("--workspace", "-w", default=None, help="Runtime workspace")
    smoke_record_advanced.add_argument("--profile", choices=["local", "staging", "production"], default=None, help="Runtime profile")
    smoke_record_advanced.add_argument("--transport", choices=["ws", "http"], default=None, help="Feishu event transport")
    smoke_record_advanced.add_argument("--scenario", required=True, choices=["image_understanding", "long_conversation", "memory_supersession", "trace2skill_promotion", "deepseek_usage", "partial_failure"], help="Advanced live scenario")
    smoke_record_advanced.add_argument("--image-ref", default=None, help="Redacted image understanding evidence reference")
    smoke_record_advanced.add_argument("--transcript-ref", default=None, help="Redacted transcript reference")
    smoke_record_advanced.add_argument("--run-id", default=None, help="Redacted runtime run id")
    smoke_record_advanced.add_argument("--memory-ref", default=None, help="Redacted memory evidence reference")
    smoke_record_advanced.add_argument("--failure-trace-ref", default=None, help="Redacted Trace2Skill failure trace reference")
    smoke_record_advanced.add_argument("--skill-ref", default=None, help="Redacted promoted skill reference")
    smoke_record_advanced.add_argument("--regression-ref", default=None, help="Redacted regression replay reference")
    smoke_record_advanced.add_argument("--regression-result-ref", default=None, help="Redacted Trace2Skill regression result reference")
    smoke_record_advanced.add_argument("--validation-ref", default=None, help="Redacted Trace2Skill regression validation reference")
    smoke_record_advanced.add_argument("--promotion-status", default=None, choices=["proven", "stable"], help="Trace2Skill promotion status")
    smoke_record_advanced.add_argument("--post-promotion-run-ref", default=None, help="Redacted post-promotion run evidence reference")
    smoke_record_advanced.add_argument("--usage-ref", default=None, help="Redacted model usage evidence reference")
    smoke_record_advanced.add_argument("--model-usage", default=None, help="JSON object with redacted token/cost usage")
    smoke_record_advanced.add_argument("--failure-ref", default=None, help="Redacted partial failure evidence reference")
    smoke_record_advanced.add_argument("--json", action="store_true", help="Output JSON")
    smoke_bundle = smoke_sub.add_parser("bundle", help="Build a redacted live smoke evidence bundle")
    smoke_bundle.add_argument("--config", "-c", default=None, help="JSON or KEY=VALUE config file")
    smoke_bundle.add_argument("--workspace", "-w", default=None, help="Runtime workspace")
    smoke_bundle.add_argument("--profile", choices=["local", "staging", "production"], default=None, help="Runtime profile")
    smoke_bundle.add_argument("--transport", choices=["ws", "http"], default=None, help="Feishu event transport")
    smoke_bundle.add_argument("--output", "-o", required=True, help="Output directory for the redacted bundle")
    smoke_bundle.add_argument("--handoff-dir", default=None, help="Optional runs directory containing run handoff.json files")
    smoke_bundle.add_argument("--live-attestation-id", default="", help="Redacted operator attestation id for a real live Feishu smoke run")
    smoke_bundle.add_argument("--feishu-app-id-hash", default="", help="Hash of the live Feishu app id used for the smoke run")
    smoke_bundle.add_argument("--tenant-hash", default="", help="Hash of the live Feishu tenant used for the smoke run")
    smoke_bundle.add_argument("--ws-sdk-session-id", default="", help="Redacted Feishu ws SDK session id for the live smoke run")
    smoke_bundle.add_argument("--json", action="store_true", help="Output JSON")
    smoke_wait = smoke_sub.add_parser("wait", help="Wait until the 1.0 live smoke evidence chain is complete")
    smoke_wait.add_argument("--config", "-c", default=None, help="JSON or KEY=VALUE config file")
    smoke_wait.add_argument("--workspace", "-w", default=None, help="Runtime workspace")
    smoke_wait.add_argument("--profile", choices=["local", "staging", "production"], default=None, help="Runtime profile")
    smoke_wait.add_argument("--transport", choices=["ws", "http"], default=None, help="Feishu event transport")
    smoke_wait.add_argument("--timeout", type=float, default=300, help="Maximum seconds to wait")
    smoke_wait.add_argument("--interval", type=float, default=2, help="Polling interval in seconds")
    smoke_wait.add_argument("--json", action="store_true", help="Output JSON")
    smoke_status = smoke_sub.add_parser("status", help="Print a read-only live smoke evidence status")
    smoke_status.add_argument("--config", "-c", default=None, help="JSON or KEY=VALUE config file")
    smoke_status.add_argument("--workspace", "-w", default=None, help="Runtime workspace")
    smoke_status.add_argument("--profile", choices=["local", "staging", "production"], default=None, help="Runtime profile")
    smoke_status.add_argument("--transport", choices=["ws", "http"], default=None, help="Feishu event transport")
    smoke_status.add_argument("--json", action="store_true", help="Output JSON")
    smoke_reset = smoke_sub.add_parser("reset", help="Clear runtime smoke evidence files before a fresh live run")
    smoke_reset.add_argument("--config", "-c", default=None, help="JSON or KEY=VALUE config file")
    smoke_reset.add_argument("--workspace", "-w", default=None, help="Runtime workspace")
    smoke_reset.add_argument("--profile", choices=["local", "staging", "production"], default=None, help="Runtime profile")
    smoke_reset.add_argument("--transport", choices=["ws", "http"], default=None, help="Feishu event transport")
    smoke_reset.add_argument("--confirm-reset", action="store_true", help="Required confirmation to clear evidence files")
    smoke_reset.add_argument("--json", action="store_true", help="Output JSON")

    config_p = sub.add_parser("config", help="Runtime configuration helpers")
    config_sub = config_p.add_subparsers(dest="config_command")
    config_template = config_sub.add_parser("template", help="Print a runtime config template")
    config_template.add_argument("--workspace", "-w", default="./workspace", help="Runtime workspace path in the template")
    config_template.add_argument("--live-smoke", action="store_true", help="Enable smoke_mode and include live smoke steps")

    diagnose_p = sub.add_parser("diagnose", help="Summarize runtime health from local JSONL records")
    diagnose_p.add_argument("--config", "-c", default=None, help="JSON or KEY=VALUE config file")
    diagnose_p.add_argument("--workspace", "-w", default=None, help="Runtime workspace")
    diagnose_p.add_argument("--json", action="store_true", help="Output JSON")

    diagnose_p.add_argument("--profile", choices=["local", "staging", "production"], default=None, help="Runtime profile")
    diagnose_p.add_argument("--transport", choices=["ws", "http"], default=None, help="Feishu event transport")

    args = parser.parse_args()

    if args.command == "init":
        target = args.workspace or os.getcwd()
        if args.personal:
            init_personal(target)
        else:
            init_standard(target)
        return

    if args.command == "serve":
        try:
            cfg = RuntimeConfig.load(
                args.config,
                profile=args.profile,
                transport=args.transport,
                workspace=args.workspace,
                host=args.host,
                port=args.port,
            )
            cfg.validate(require_secrets=True)
            if args.dry_run:
                print("YINYO runtime config OK")
                print(redact_config(cfg))
                return
            serve(cfg)
        except ConfigError as exc:
            print(f"Config error: {exc}", file=sys.stderr)
            raise SystemExit(2)

    if args.command == "smoke" and args.smoke_command == "verify":
        from .smoke import verify_smoke_evidence_file

        cfg = None
        if args.config or args.workspace or args.profile or args.transport:
            cfg = RuntimeConfig.load(
                args.config,
                profile=args.profile,
                transport=args.transport,
                workspace=args.workspace,
            )
        path = args.path or (cfg.smoke_evidence_path if cfg else os.path.join(os.getcwd(), "workspace", "smoke_evidence.jsonl"))
        transport = cfg.transport if cfg else args.transport
        result = verify_smoke_evidence_file(path, transport=transport)
        if args.json:
            import json

            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            status = "OK" if result.get("ok") else "INCOMPLETE"
            advanced = result.get("advanced", {})
            basic = result.get("basic", {})
            print(f"YINYO smoke evidence verify: {status}")
            print(f"path: {path}")
            print(f"transport: {transport or ''}")
            print(f"basic_missing: {basic.get('missing', [])}")
            print(f"advanced_missing: {advanced.get('missing', [])}")
            print(f"advanced_field_missing: {advanced.get('field_missing', [])}")
            print(f"advanced_source_missing: {advanced.get('source_missing', [])}")
            print(f"advanced_proof_missing: {advanced.get('proof_missing', [])}")
            print(f"advanced_proof_mismatch: {advanced.get('proof_mismatch', [])}")
            print(f"advanced_ref_unresolved: {advanced.get('ref_unresolved', [])}")
            print(f"records: {result.get('records', 0)}")
            if not result.get("ok"):
                status_command = f"yinyo smoke status --config {args.config} --json" if args.config else (
                    f"yinyo smoke status --workspace {cfg.workspace} --transport {transport} --json" if cfg else "yinyo smoke status --json"
                )
                print(f"next: {status_command}")
        if not result["ok"]:
            raise SystemExit(1)
        return

    if args.command == "smoke" and args.smoke_command == "plan":
        from .smoke import REQUIRED_1_0_ADVANCED_SCENARIOS, required_live_smoke_scenarios

        path = args.path or os.path.join(os.getcwd(), "workspace", "smoke_evidence.jsonl")
        print("YINYO 1.0 live smoke plan")
        print(f"evidence_path: {path}")
        print(f"transport: {args.transport}")
        print("basic live scenarios:")
        for scenario in sorted(required_live_smoke_scenarios(args.transport)):
            print(f"- {scenario}")
        print("\nadvanced live scenarios:")
        for scenario in sorted(REQUIRED_1_0_ADVANCED_SCENARIOS):
            print(f"- {scenario}")
        print("\nverify:")
        print(f"yinyo smoke verify --transport {args.transport} --path {path}")
        print("# --smoke-path is diagnostic only; the 1.0 gate requires config or a verified redacted bundle.")
        print("python scripts/verify_release.py --target 1.0.0 --config ./yinyo.env")
        print("yinyo smoke bundle --config ./yinyo.env --output ./workspace/smoke-bundle --handoff-dir ./workspace/runs --live-attestation-id <attestation-id> --tenant-hash <sha256-tenant>")
        print("python scripts/verify_release.py --target 1.0.0 --bundle ./workspace/smoke-bundle --candidate 1.0.0")
        return

    if args.command == "smoke" and args.smoke_command == "preflight":
        from .preflight import format_preflight, run_preflight

        cfg = RuntimeConfig.load(
            args.config,
            profile=args.profile,
            transport=args.transport,
            workspace=args.workspace,
        )
        result = run_preflight(cfg, allow_existing_evidence=args.allow_existing_evidence)
        if args.json:
            import json

            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(format_preflight(result))
        if not result["ok"]:
            raise SystemExit(1)
        return

    if args.command == "smoke" and args.smoke_command == "runbook":
        from .smoke import build_live_smoke_runbook, format_live_smoke_runbook

        cfg = RuntimeConfig.load(
            args.config,
            profile=args.profile,
            transport=args.transport,
            workspace=args.workspace,
        )
        runbook = build_live_smoke_runbook(cfg, config_path=args.config or "./yinyo.env")
        if args.json:
            import json

            print(json.dumps(runbook, ensure_ascii=False, indent=2))
        else:
            print(format_live_smoke_runbook(runbook))
        return

    if args.command == "smoke" and args.smoke_command == "record-advanced":
        from .smoke import record_advanced_live_evidence

        cfg = RuntimeConfig.load(
            args.config,
            profile=args.profile,
            transport=args.transport,
            workspace=args.workspace,
        )
        fields = {
            "image_ref": args.image_ref,
            "transcript_ref": args.transcript_ref,
            "run_id": args.run_id,
            "memory_ref": args.memory_ref,
            "failure_trace_ref": args.failure_trace_ref,
            "skill_ref": args.skill_ref,
            "regression_ref": args.regression_ref,
            "regression_result_ref": args.regression_result_ref,
            "validation_ref": args.validation_ref,
            "promotion_status": args.promotion_status,
            "post_promotion_run_ref": args.post_promotion_run_ref,
            "usage_ref": args.usage_ref,
            "failure_ref": args.failure_ref,
        }
        if args.model_usage:
            import json

            try:
                model_usage = json.loads(args.model_usage)
            except json.JSONDecodeError as exc:
                print(f"Advanced evidence refused: model_usage must be a JSON object: {exc}", file=sys.stderr)
                raise SystemExit(2)
            if not isinstance(model_usage, dict):
                print("Advanced evidence refused: model_usage must be a JSON object", file=sys.stderr)
                raise SystemExit(2)
            fields["model_usage"] = model_usage
        try:
            result = record_advanced_live_evidence(cfg.smoke_evidence_path, args.scenario, **fields)
        except ValueError as exc:
            print(f"Advanced evidence refused: {exc}", file=sys.stderr)
            raise SystemExit(2)
        if args.json:
            import json

            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            advanced = result["advanced"]
            status = "OK" if advanced.get("ok") else "INCOMPLETE"
            print(f"YINYO advanced live evidence recorded: {args.scenario}")
            print(f"advanced_status: {status}")
            print(f"missing: {advanced.get('missing', [])}")
            print(f"field_missing: {advanced.get('field_missing', [])}")
            print(f"source_missing: {advanced.get('source_missing', [])}")
            print(f"ref_unresolved: {advanced.get('ref_unresolved', [])}")
        return

    if args.command == "smoke" and args.smoke_command == "bundle":
        from .smoke import build_smoke_evidence_bundle

        cfg = RuntimeConfig.load(
            args.config,
            profile=args.profile,
            transport=args.transport,
            workspace=args.workspace,
        )
        config_ws_session_id = str(getattr(cfg, "ws_sdk_session_id", "") or "").strip()
        arg_ws_session_id = str(args.ws_sdk_session_id or "").strip()
        ws_sdk_session_id = arg_ws_session_id or config_ws_session_id
        if cfg.transport == "ws" and arg_ws_session_id and config_ws_session_id and arg_ws_session_id != config_ws_session_id:
            raise SystemExit(
                "smoke bundle --ws-sdk-session-id must match ws_sdk_session_id from config; "
                "use one live provenance session marker for service_start, ws_transport_start, and the bundle manifest"
            )
        config_app_id_hash = _sha256_text(getattr(cfg, "app_id", ""))
        arg_app_id_hash = str(args.feishu_app_id_hash or "").strip()
        feishu_app_id_hash = arg_app_id_hash or config_app_id_hash
        if arg_app_id_hash and config_app_id_hash and arg_app_id_hash != config_app_id_hash:
            raise SystemExit(
                "smoke bundle --feishu-app-id-hash must match sha256(app_id) from config; "
                "use one live provenance app marker for the bundle manifest"
            )
        manifest = build_smoke_evidence_bundle(
            output_dir=args.output,
            smoke_path=cfg.smoke_evidence_path,
            log_path=cfg.log_path,
            job_store_path=cfg.job_store_path,
            event_store_path=cfg.event_store_path,
            runtime_lock_path=cfg.runtime_lock_path,
            profile=cfg.profile,
            transport=cfg.transport,
            config_path=args.config or "./yinyo.env",
            handoff_dir=args.handoff_dir or "",
            live_attestation_id=args.live_attestation_id,
            feishu_app_id_hash=feishu_app_id_hash,
            tenant_hash=args.tenant_hash,
            ws_sdk_session_id=ws_sdk_session_id,
        )
        if args.json:
            import json

            print(json.dumps(manifest, ensure_ascii=False, indent=2))
        else:
            status = "OK" if manifest.get("ok") else "ATTENTION"
            advanced = manifest.get("advanced", {})
            diagnostics = manifest.get("diagnostics", {})
            diagnostic_alerts = diagnostics.get("alerts", [])
            if diagnostics.get("error"):
                diagnostic_alerts = [diagnostics["error"]]
            print(f"YINYO smoke evidence bundle: {status}")
            print(f"output: {args.output}")
            print(f"chain_missing: {manifest.get('chain', {}).get('missing', [])}")
            print(f"advanced_missing: {advanced.get('missing', [])}")
            print(f"advanced_field_missing: {advanced.get('field_missing', [])}")
            print(f"advanced_source_missing: {advanced.get('source_missing', [])}")
            print(f"advanced_proof_missing: {advanced.get('proof_missing', [])}")
            print(f"advanced_proof_mismatch: {advanced.get('proof_mismatch', [])}")
            print(f"advanced_ref_unresolved: {advanced.get('ref_unresolved', [])}")
            print(f"diagnostics_alerts: {diagnostic_alerts}")
            runtime_verification = manifest.get("runtime_verification", {})
            if runtime_verification.get("blockers"):
                print(f"runtime_verification_blockers: {runtime_verification.get('blockers', [])}")
            provenance_verification = manifest.get("live_provenance_verification", {})
            if provenance_verification.get("blockers"):
                print(f"live_provenance_blockers: {provenance_verification.get('blockers', [])}")
            frontier = manifest.get("frontier_readiness", {})
            if frontier:
                print(f"frontier_readiness: {frontier.get('ok') is True}")
                print(f"frontier_blockers: {frontier.get('operator_blockers', [])}")
            if cfg.transport == "ws" and not args.handoff_dir:
                handoff_dir = Path(cfg.workspace) / "runs"
                print(f"candidate_warning: candidate 1.0.0 will fail without run handoffs; rerun with --handoff-dir {handoff_dir}")
            provenance = manifest.get("live_provenance", {})
            missing_provenance = [
                name
                for name in ("operator_attestation_id", "feishu_app_id_hash", "tenant_hash")
                if not provenance.get(name)
            ]
            if cfg.transport == "ws" and not provenance.get("ws_sdk_session_id"):
                missing_provenance.append("ws_sdk_session_id")
            if missing_provenance:
                print(f"candidate_warning: candidate 1.0.0 will fail without live provenance fields: {missing_provenance}")
            if manifest.get("operator_next_actions"):
                print("operator_next_actions:")
                for item in manifest["operator_next_actions"]:
                    print(f"- {item}")
            if manifest.get("operator_plan"):
                print("operator_plan:")
                for item in manifest["operator_plan"]:
                    print(f"- [{item['layer']}] {item['scenario']}: {item['command']}")
            handoff = manifest.get("handoff_summary", {})
            if handoff:
                print(f"handoff_blocking_layers: {handoff.get('blocking_layers', [])}")
        if not manifest.get("ok"):
            raise SystemExit(1)
        return

    if args.command == "smoke" and args.smoke_command == "wait":
        from .smoke import required_live_smoke_scenarios, wait_for_smoke_evidence_chain

        cfg = RuntimeConfig.load(
            args.config,
            profile=args.profile,
            transport=args.transport,
            workspace=args.workspace,
        )
        result = wait_for_smoke_evidence_chain(
            smoke_path=cfg.smoke_evidence_path,
            log_path=cfg.log_path,
            job_store_path=cfg.job_store_path,
            event_store_path=cfg.event_store_path,
            runtime_lock_path=cfg.runtime_lock_path,
            transport=cfg.transport,
            config_path=args.config or "./yinyo.env",
            timeout_seconds=args.timeout,
            interval_seconds=args.interval,
            required=set(required_live_smoke_scenarios(cfg.transport)),
        )
        if args.json:
            import json

            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            status = "OK" if result.get("ok") else "TIMEOUT"
            print(f"YINYO smoke evidence wait: {status}")
            print(f"attempts: {result.get('attempts')}")
            print(f"missing: {result.get('chain', {}).get('missing', [])}")
            print(f"advanced_missing: {result.get('chain', {}).get('advanced', {}).get('missing', [])}")
            print(f"advanced_field_missing: {result.get('chain', {}).get('advanced', {}).get('field_missing', [])}")
            print(f"advanced_source_missing: {result.get('chain', {}).get('advanced', {}).get('source_missing', [])}")
            print(f"advanced_ref_unresolved: {result.get('chain', {}).get('advanced', {}).get('ref_unresolved', [])}")
            if result.get("operator_next_actions"):
                print("operator_next_actions:")
                for item in result["operator_next_actions"]:
                    print(f"- {item}")
            if result.get("operator_plan"):
                print("operator_plan:")
                for item in result["operator_plan"]:
                    print(f"- [{item['layer']}] {item['scenario']}: {item['command']}")
            handoff = result.get("handoff_summary", {})
            if handoff:
                print(f"handoff_blocking_layers: {handoff.get('blocking_layers', [])}")
        if not result.get("ok"):
            raise SystemExit(1)
        return

    if args.command == "smoke" and args.smoke_command == "status":
        from .smoke import build_smoke_evidence_status, required_live_smoke_scenarios

        cfg = RuntimeConfig.load(
            args.config,
            profile=args.profile,
            transport=args.transport,
            workspace=args.workspace,
        )
        result = build_smoke_evidence_status(
            smoke_path=cfg.smoke_evidence_path,
            log_path=cfg.log_path,
            job_store_path=cfg.job_store_path,
            event_store_path=cfg.event_store_path,
            runtime_lock_path=cfg.runtime_lock_path,
            profile=cfg.profile,
            transport=cfg.transport,
            config_path=args.config or "./yinyo.env",
            required=set(required_live_smoke_scenarios(cfg.transport)),
        )
        if args.json:
            import json

            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            status = "OK" if result.get("ok") else "INCOMPLETE"
            print(f"YINYO smoke evidence status: {status}")
            for item in result["scenarios"]:
                marker = "OK" if item["ok"] else "MISSING"
                print(f"- {item['scenario']}: {marker} {item['missing']}")
            print("advanced_scenarios:")
            for item in result["advanced_scenarios"]:
                marker = "OK" if item["ok"] else "MISSING"
                print(f"- {item['scenario']}: {marker} {item['missing']}")
            if result["next_actions"]:
                print("next_actions:")
                for item in result["next_actions"]:
                    print(f"- {item}")
            if result.get("operator_plan"):
                print("operator_plan:")
                for item in result["operator_plan"]:
                    print(f"- [{item['layer']}] {item['scenario']}: {item['command']}")
            recovery = result.get("recovery_summary", {})
            if recovery:
                print(
                    "recovery_summary: "
                    f"service_last_status={recovery.get('service_last_status')}, "
                    f"runtime_lock_status={recovery.get('runtime_lock_status')}, "
                    f"failed_jobs={recovery.get('failed_jobs')}, "
                    f"ack_deadline_misses={recovery.get('ack_deadline_misses')}"
                )
            handoff = result.get("handoff_summary", {})
            if handoff:
                print(f"handoff_blocking_layers: {handoff.get('blocking_layers', [])}")
        if not result.get("ok"):
            raise SystemExit(1)
        return

    if args.command == "smoke" and args.smoke_command == "reset":
        from .smoke import reset_smoke_evidence_files

        cfg = RuntimeConfig.load(
            args.config,
            profile=args.profile,
            transport=args.transport,
            workspace=args.workspace,
        )
        try:
            result = reset_smoke_evidence_files(
                smoke_path=cfg.smoke_evidence_path,
                log_path=cfg.log_path,
                job_store_path=cfg.job_store_path,
                event_store_path=cfg.event_store_path,
                confirm=args.confirm_reset,
            )
        except ValueError as exc:
            print(f"Reset refused: {exc}", file=sys.stderr)
            raise SystemExit(2)
        if args.json:
            import json

            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("YINYO smoke evidence reset: OK")
            for name, item in result["reset"].items():
                print(f"- {name}: {item['path']} ({item['previous_bytes']} bytes cleared)")
        return

    if args.command == "config" and args.config_command == "template":
        print(build_config_template(live_smoke=args.live_smoke, workspace=args.workspace), end="")
        return

    if args.command == "diagnose":
        from .diagnostics import format_diagnostics, summarize_runtime

        cfg = RuntimeConfig.load(args.config, profile=args.profile, transport=args.transport, workspace=args.workspace)
        summary = summarize_runtime(
            log_path=cfg.log_path,
            job_store_path=cfg.job_store_path,
            smoke_evidence_path=cfg.smoke_evidence_path,
            event_store_path=cfg.event_store_path,
            runtime_lock_path=cfg.runtime_lock_path,
            transport=cfg.transport,
        )
        if args.json:
            import json

            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print(format_diagnostics(summary))
        if not summary["ok"]:
            raise SystemExit(1)
        return

    parser.print_help()


def _sha256_text(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    main()
