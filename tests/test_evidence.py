# test_evidence.py — 证据引擎测试（EvidenceLedger + VerificationGate）
"""测试 evidence 模块的证据记录和验证功能。"""

import pytest, json, os, tempfile
from evidence import EvidenceLedger, VerificationGate, RunManifest


class TestEvidenceLedger:
    """EvidenceLedger JSONL 记录测试。"""

    @pytest.fixture
    def ledger(self, tmp_path):
        run_dir = str(tmp_path / "runs" / "test-run-001")
        return EvidenceLedger(run_dir)

    def test_record_basic(self, ledger):
        """基本记录：工具调用应生成 evidence ref。"""
        ref = ledger.record(
            run_id="run-001", step=1, tool="do_read",
            args={"path": "test.txt"}, result={"content": "hello"}
        )
        assert ref, "应返回 evidence ref hash"
        assert len(ref) == 12, f"hash 应为 12 字符，实际 {len(ref)}"

    def test_record_multiple_steps(self, ledger):
        """多次记录应追加到同一 JSONL 文件。"""
        ledger.record("run-001", 1, "do_read", {"path": "a.txt"}, {"content": "a"})
        ledger.record("run-001", 2, "do_write", {"path": "b.txt", "content": "b"}, {"wrote": 1})

        with open(ledger.path, "r") as f:
            lines = f.readlines()
        assert len(lines) == 2, f"应有 2 条记录，实际 {len(lines)}"

    def test_record_redacts_sensitive_args(self, ledger):
        """敏感参数应被脱敏。"""
        ledger.record("run-001", 1, "do_ask",
                      {"api_key": "sk-projABCDEFGHIJKLMNOPQRSTUVWXYZ"},
                      {"answer": "done"})

        with open(ledger.path, "r") as f:
            record = json.loads(f.readline())
        args_str = json.dumps(record["args"])
        assert "sk-proj" not in args_str, "密钥不应以明文记录"


class TestVerificationGate:
    """VerificationGate 三态验证测试。"""

    def test_dowrite_hash_match(self, tmp_path):
        """do_write 哈希匹配 → verified。"""
        gate = VerificationGate()
        path = str(tmp_path / "test.txt")
        with open(path, "w") as f:
            f.write("hello")

        import hashlib
        h = "sha256:" + hashlib.sha256(b"hello").hexdigest()[:16]
        result = gate.verify({
            "tool": "do_write",
            "args": {"path": path},
            "result": {"hash": h, "wrote": 5},
        })
        assert result.status == "verified"

    def test_dowrite_hash_mismatch(self, tmp_path):
        """do_write 哈希不匹配 → blocked。"""
        gate = VerificationGate()
        path = str(tmp_path / "test2.txt")
        with open(path, "w") as f:
            f.write("real content")

        result = gate.verify({
            "tool": "do_write",
            "args": {"path": path},
            "result": {"hash": "sha256:0000000000000000", "wrote": 13},
        })
        assert result.status == "blocked"

    def test_dorun_nonzero_exit(self):
        """do_run 非零退出 → blocked。"""
        gate = VerificationGate()
        result = gate.verify({
            "tool": "do_run",
            "result": {"exit_code": 1, "stderr": "error"},
        })
        assert result.status == "blocked"

    def test_dorun_zero_exit(self):
        """do_run 零退出 → verified。"""
        gate = VerificationGate()
        result = gate.verify({
            "tool": "do_run",
            "result": {"exit_code": 0, "stdout": "ok"},
        })
        assert result.status == "verified"

    def test_blocked_propagation(self):
        """被 governance 拦截的结果应传播 blocked。"""
        gate = VerificationGate()
        result = gate.verify({
            "tool": "do_write",
            "result": {"_blocked": True, "error": "Blocked by risk policy"},
        })
        assert result.status == "blocked"

    def test_pending(self):
        """pending 标志应传播。"""
        gate = VerificationGate()
        result = gate.verify({
            "tool": "do_read",
            "result": {"_pending": True},
        })
        assert result.status == "pending"


class TestRunManifest:
    """RunManifest 生命周期测试。"""

    def test_create_manifest(self, tmp_path):
        run_dir = str(tmp_path / "runs" / "test-run")
        rm = RunManifest(run_dir)
        m = rm.create("run-001", "test task")

        assert m["run_id"] == "run-001"
        assert m["task"] == "test task"
        assert m["status"] == "running"
        assert os.path.isfile(rm.path)

    def test_update_manifest(self, tmp_path):
        run_dir = str(tmp_path / "runs" / "test-run")
        rm = RunManifest(run_dir)
        rm.create("run-002", "another task")
        rm.update(status="completed", steps=10)

        with open(rm.path) as f:
            m = json.load(f)
        assert m["status"] == "completed"
        assert m["steps"] == 10
