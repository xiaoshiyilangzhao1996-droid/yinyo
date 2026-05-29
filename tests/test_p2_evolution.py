# test_p2_evolution.py - P2 evolution acceptance checks from docs/spec.md

import json
import sys


def test_trace2skill_writes_regression_fixture(tmp_path):
    from yinyo import ModelGateway
    from yinyo.evolution import FailurePattern, SkillEvolution

    model = ModelGateway(api_key="")
    model.set_mock_responses([
        {"content": json.dumps({
            "name": "retry-file-write",
            "description": "Handle repeated file write failures safely.",
            "steps": ["Check workspace", "Request confirmation", "Verify evidence"],
            "triggers": ["write", "confirm"],
            "pitfalls": ["Do not bypass confirmation"],
        }), "finish_reason": "stop"},
    ])
    se = SkillEvolution(str(tmp_path), model=model)
    pattern = FailurePattern(
        task_keywords=["write", "file"],
        error_message="Confirmation required",
        occurrence_count=2,
        last_occurred="2026-05-27T00:00:00+00:00",
    )

    skill = se.extract_skill_from_failure(pattern, "write file", "Confirmation required")

    regression_path = tmp_path / "skills" / skill.name / "regression.json"
    regression = json.loads(regression_path.read_text(encoding="utf-8"))
    assert regression["schema"] == "yinyo.trace2skill_regression.v1"
    assert regression["skill_name"] == skill.name
    assert regression["task"] == "write file"
    assert regression["error"] == "Confirmation required"
    assert regression["expected_failure"] == "Confirmation required"
    assert regression["pre_skill_expected_status"] == "failed"
    assert regression["post_skill_expected_status"] == "guarded"
    assert regression["pre_skill_command"]
    assert regression["post_skill_command"]
    assert regression["replay_command"]
    assert regression["failure_trace_ref"].startswith("trace2skill:")
    assert regression["validation_required"] is True
    assert regression["guardrail_application_required"] is True
    assert regression["pattern_keywords"] == ["write", "file"]
    assert "Do not bypass confirmation" in regression["expected_guardrails"]


def test_trace2skill_regression_replay_records_refs_and_promotes(tmp_path):
    from yinyo import ModelGateway
    from yinyo.evolution import FailurePattern, SkillEvolution

    model = ModelGateway(api_key="")
    model.set_mock_responses([
        {"content": json.dumps({
            "name": "retry-file-write",
            "description": "Handle repeated file write failures safely.",
            "steps": ["Check workspace", "Request confirmation", "Verify evidence"],
            "triggers": ["write", "confirm"],
            "pitfalls": ["Do not bypass confirmation"],
        }), "finish_reason": "stop"},
    ])
    se = SkillEvolution(str(tmp_path), model=model)
    pattern = FailurePattern(
        task_keywords=["write", "confirm"],
        error_message="Confirmation required",
        occurrence_count=2,
        last_occurred="2026-05-27T00:00:00+00:00",
    )
    skill = se.extract_skill_from_failure(pattern, "write a file", "Confirmation required")

    validation = se.validate_skill_regression(skill.name)
    promotion = se.promote_skill_after_validation(skill.name, validation)
    meta = json.loads((tmp_path / "skills" / skill.name / "meta.json").read_text(encoding="utf-8"))
    saved_validation = json.loads((tmp_path / "skills" / skill.name / "validation" / f"{validation['run_id']}.json").read_text(encoding="utf-8"))

    assert validation["schema"] == "yinyo.trace2skill_validation.v1"
    assert validation["passed"] is True
    assert validation["failure_trace_ref"].startswith("trace2skill:")
    assert validation["regression_ref"].endswith("regression.json")
    assert validation["replay_result"]["exit_code"] == 0
    assert "failure_replayed=Confirmation required" in validation["replay_result"]["stdout_tail"]
    assert "Do not bypass confirmation" in validation["replay_result"]["stdout_tail"]
    assert validation["checks"]["replay_command_passed"] is True
    assert validation["checks"]["replay_output_mentions_failure"] is True
    assert validation["checks"]["replay_output_mentions_guardrail"] is True
    assert validation["checks"]["pre_skill_failure_reproduced"] is True
    assert validation["checks"]["post_skill_guardrail_applied"] is True
    assert validation["checks"]["pre_skill_command_failed_as_expected"] is True
    assert validation["checks"]["pre_skill_output_mentions_failure"] is True
    assert validation["checks"]["post_skill_command_passed"] is True
    assert validation["checks"]["post_skill_output_mentions_guardrail"] is True
    assert validation["harness_result"]["schema"] == "yinyo.trace2skill_regression_harness.v1"
    assert validation["harness_result"]["pre_skill_status"] == "failed"
    assert validation["harness_result"]["post_skill_status"] == "guarded"
    assert validation["harness_result"]["guardrail_applied"] is True
    assert validation["pre_skill_result"]["exit_code"] != 0
    assert validation["pre_skill_result"]["path"]
    assert validation["post_skill_result"]["exit_code"] == 0
    assert validation["post_skill_result"]["path"]
    assert validation["pre_skill_result"]["path"] != validation["post_skill_result"]["path"]
    assert saved_validation["checks"]["skill_bound"] is True
    assert saved_validation["harness_result"]["guardrail_applied"] is True
    assert saved_validation["post_skill_result"]["passed"] is True
    assert promotion["schema"] == "yinyo.trace2skill_promotion.v1"
    assert promotion["promoted"] is True
    assert promotion["validation_ref"] == validation["path"]
    assert meta["status"] == "proven"
    assert meta["validation_ref"] == validation["path"]


def test_trace2skill_regression_replay_blocks_promotion_on_failure(tmp_path):
    from yinyo import ModelGateway
    from yinyo.evolution import FailurePattern, SkillEvolution

    model = ModelGateway(api_key="")
    model.set_mock_responses([
        {"content": json.dumps({
            "name": "retry-file-write",
            "description": "Handle repeated file write failures safely.",
            "steps": ["Check workspace"],
            "triggers": ["write"],
            "pitfalls": [],
        }), "finish_reason": "stop"},
    ])
    se = SkillEvolution(str(tmp_path), model=model)
    pattern = FailurePattern(
        task_keywords=["write", "confirm"],
        error_message="Confirmation required",
        occurrence_count=2,
        last_occurred="2026-05-27T00:00:00+00:00",
    )
    skill = se.extract_skill_from_failure(pattern, "write a file", "Confirmation required")

    validation = se.validate_skill_regression(skill.name)
    promotion = se.promote_skill_after_validation(skill.name, validation)
    meta = json.loads((tmp_path / "skills" / skill.name / "meta.json").read_text(encoding="utf-8"))

    assert validation["passed"] is False
    assert validation["checks"]["guardrails_present"] is False
    assert validation["checks"]["post_skill_guardrail_applied"] is False
    assert validation["checks"]["post_skill_command_passed"] is False
    assert promotion["promoted"] is False
    assert meta["status"] == "draft"


def test_blind_test_runner_records_real_subprocess_evidence(tmp_path):
    from yinyo import BlindTestRunner

    runner = BlindTestRunner(str(tmp_path))
    command = [sys.executable, "-c", "print('blind-ok')"]

    record = runner.run("run-001", command, timeout=30)

    path = tmp_path / "validation" / "run-001.json"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert record["passed"] is True
    assert saved["exit_code"] == 0
    assert "blind-ok" in saved["stdout_tail"]
    assert saved["command"] == command


def test_context_retention_report_tracks_masking_and_protected_tail(tmp_path):
    from yinyo.context import ContextManager

    ctx = ContextManager(max_tokens=80, keep_tail=4, cache_dir=str(tmp_path / "cache"))
    for i in range(20):
        ctx.messages.append({"role": "tool", "content": f"old observation {i} " + ("x" * 50)})
    ctx.messages.append({"role": "user", "content": "PROTECTED_RECENT_MESSAGE"})

    before = ctx.retention_report(["PROTECTED_RECENT_MESSAGE"])
    ctx.auto_manage(step=1)
    after = ctx.retention_report(["PROTECTED_RECENT_MESSAGE"])

    assert before["estimated_tokens"] > 80
    assert after["masked_observations"] > 0
    assert after["protected_present"]["PROTECTED_RECENT_MESSAGE"] is True
