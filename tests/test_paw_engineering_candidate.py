from __future__ import annotations
import hashlib
import subprocess
import pytest
from pathlib import Path

from agentos_node.paw_engineering_candidate import apply_bounded_test_candidate
from agentos_node.paw_engineering_worktree import PreparedPawWorktree, PawWorktreeBoundaryError


def candidate(tmp_path):
    root = tmp_path / "worktree"
    (root / "tests").mkdir(parents=True)
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
    p = root / "tests/test_paw_engineering_worktree.py"
    p.write_text("def test_one():\n    assert True\n")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-m", "base"], check=True, capture_output=True)
    sha = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], text=True, capture_output=True, check=True).stdout.strip()
    return PreparedPawWorktree(root, "paw/470/work-a", sha), p


def test_candidate_fixed_pytest_receipt(tmp_path):
    w, p = candidate(tmp_path)
    expected = hashlib.sha256(p.read_bytes()).hexdigest()
    r = apply_bounded_test_candidate(w, relative_path="tests/test_paw_engineering_worktree.py",
                                      expected_sha256=expected, replacement="def test_one():\n    assert True\n\ndef test_two():\n    assert 1 + 1 == 2\n")
    assert r.test_pass
    assert r.test_exit_code == 0
    assert r.independent_acceptance_pass is False
    assert "test_two" in p.read_text()


def test_candidate_rejects_wrong_path_and_stale_hash(tmp_path):
    w, p = candidate(tmp_path)
    with pytest.raises(PawWorktreeBoundaryError, match="path_not_authorized"):
        apply_bounded_test_candidate(w, relative_path="../main.py", expected_sha256="bad", replacement="x")
    with pytest.raises(PawWorktreeBoundaryError, match="base_mismatch"):
        apply_bounded_test_candidate(w, relative_path="tests/test_paw_engineering_worktree.py",
                                      expected_sha256="bad", replacement="def test_one():\n    pass\n")
    assert "assert True" in p.read_text()


def test_candidate_failed_test_not_accepted(tmp_path):
    w, p = candidate(tmp_path)
    r = apply_bounded_test_candidate(w, relative_path="tests/test_paw_engineering_worktree.py",
                                      expected_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                                      replacement="def test_one():\n    assert False\n")
    assert r.test_pass is False
    assert r.independent_acceptance_pass is False


@pytest.mark.parametrize("malicious", [
    "import os\ndef test_one():\n    assert True\n",
    "def test_one():\n    __import__('os').system('echo escaped')\n",
    "def test_one():\n    assert open('/etc/passwd')\n",
    "def test_one():\n    assert (1).__class__\n",
    "@staticmethod\ndef test_one():\n    assert True\n",
    "def test_one():\n    assert True\n\nx = 42\n",
])
def test_candidate_rejects_executable_python_before_write(tmp_path, malicious):
    w, p = candidate(tmp_path)
    initial = p.read_bytes()
    with pytest.raises(PawWorktreeBoundaryError, match="paw_patch_"):
        apply_bounded_test_candidate(
            w, relative_path="tests/test_paw_engineering_worktree.py",
            expected_sha256=hashlib.sha256(initial).hexdigest(),
            replacement=malicious,
        )
    assert p.read_bytes() == initial
