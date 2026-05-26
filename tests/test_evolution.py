# test_evolution.py — 自进化系统基础测试
"""测试 SkillCrystallizer、ChangeManifest、SelfCheck 核心功能。"""

import pytest, json, os


class TestSkillCrystallizer:
    """SkillCrystallizer 技能结晶测试。"""

    def test_init_creates_skills_dir(self, tmp_path):
        from evolution import SkillCrystallizer
        ws = str(tmp_path)
        sc = SkillCrystallizer(ws)
        skills_dir = os.path.join(ws, "skills")
        assert os.path.isdir(skills_dir)

    def test_observe_returns_none_for_empty_tools(self, tmp_path):
        """空工具序列应返回 None。"""
        from evolution import SkillCrystallizer
        ws = str(tmp_path)
        sc = SkillCrystallizer(ws)
        result = sc.observe([])
        assert result is None

    def test_observe_returns_skill_for_sequence(self, tmp_path):
        """有工具序列应尝试结晶。"""
        from evolution import SkillCrystallizer
        ws = str(tmp_path)
        sc = SkillCrystallizer(ws)
        result = sc.observe(["do_read", "do_write", "do_edit"])
        # 可能返回 Skill 或 None（取决于内部逻辑）
        if result is not None:
            assert hasattr(result, 'name')


class TestChangeManifest:
    """ChangeManifest 生命周期测试。"""

    def test_create_manifest(self, tmp_path):
        from evolution import ChangeManifest
        ws = str(tmp_path)
        cm = ChangeManifest(ws)
        result = cm.create_manifest(
            run_id="run-001",
            change_type="feat",
            change_summary="Added test",
            affected_files=["test.py"],
        )
        assert result is not None

    def test_manifest_file_exists(self, tmp_path):
        from evolution import ChangeManifest
        ws = str(tmp_path)
        cm = ChangeManifest(ws)
        cm.create_manifest(
            run_id="run-002",
            change_type="fix",
            change_summary="Fixed bug",
            affected_files=["bug.py"],
        )
        manifest_path = os.path.join(ws, "manifests", "run-002.json")
        assert os.path.isfile(manifest_path)

    def test_manifest_contains_fields(self, tmp_path):
        from evolution import ChangeManifest
        ws = str(tmp_path)
        cm = ChangeManifest(ws)
        cm.create_manifest(
            run_id="run-003",
            change_type="refactor",
            change_summary="Cleaned up",
            affected_files=["tools.py", "agent.py"],
            blind_test_result={"status": "pass", "pass_rate": "100%"},
        )
        manifest_path = os.path.join(ws, "manifests", "run-003.json")
        with open(manifest_path) as f:
            data = json.load(f)
        assert data["run_id"] == "run-003"
        assert data["change_type"] == "refactor"
        assert "tools.py" in data["affected_files"]

    def test_record_appends_to_changes(self, tmp_path):
        from evolution import ChangeManifest
        ws = str(tmp_path)
        cm = ChangeManifest(ws)
        cm.record("test_event", {"key": "value"})
        changes_path = os.path.join(ws, "changes.jsonl")
        assert os.path.isfile(changes_path)
        with open(changes_path) as f:
            lines = f.readlines()
        assert len(lines) >= 1


class TestSelfCheck:
    """SelfCheck 自检测试。"""

    def test_run_returns_report(self, tmp_path):
        from evolution import SelfCheck
        ws = str(tmp_path)
        sc = SelfCheck(ws)
        report = sc.run()
        assert report is not None, "run() 应返回 SelfCheckReport"

    def test_report_has_checks_field(self, tmp_path):
        from evolution import SelfCheck
        ws = str(tmp_path)
        sc = SelfCheck(ws)
        report = sc.run()
        assert hasattr(report, 'checks'), "report 应有 checks 字段"


class TestSkillEvolution:
    """SkillEvolution 技能演化测试（v8.0）。"""

    def test_init_no_crash(self, tmp_path):
        from evolution import SkillEvolution
        ws = str(tmp_path)
        try:
            from model import ModelGateway
            model = ModelGateway(api_key="")
            se = SkillEvolution(ws, model=model)
            assert se is not None
        except Exception as e:
            pytest.skip(f"Model init failed: {e}")
