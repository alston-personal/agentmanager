import subprocess
import tempfile
import unittest
from pathlib import Path

from agentos_node.data_mirror import (
    READONLY_PUSH_SENTINEL,
    ensure_readonly_push_lock,
    sync_readonly_mirror,
    verify_readonly_mirror,
)


def _git(cwd: Path, *args: str) -> str:
    res = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True)
    return res.stdout.strip()


class EdgeDataMirrorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.remote_repo = self.root / "remote.git"
        self.seed_repo = self.root / "seed"
        self.mirror_repo = self.root / "mirror"

        _git(self.root, "init", "--bare", str(self.remote_repo))
        _git(self.root, "clone", str(self.remote_repo), str(self.seed_repo))
        _git(self.seed_repo, "config", "user.name", "Test")
        _git(self.seed_repo, "config", "user.email", "test@example.com")
        _git(self.seed_repo, "checkout", "-b", "main")
        (self.seed_repo / "README.md").write_text("v1\n", encoding="utf-8")
        _git(self.seed_repo, "add", "README.md")
        _git(self.seed_repo, "commit", "-m", "initial")
        _git(self.seed_repo, "push", "-u", "origin", "main")
        _git(self.remote_repo, "symbolic-ref", "HEAD", "refs/heads/main")

        _git(self.root, "clone", str(self.remote_repo), str(self.mirror_repo))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_verify_fails_before_push_lock(self) -> None:
        res = verify_readonly_mirror(self.mirror_repo)
        self.assertFalse(res["compliant"])
        self.assertEqual(res["reason"], "push_not_disabled")

    def test_lock_disables_push_and_passes_verify(self) -> None:
        lock_res = ensure_readonly_push_lock(self.mirror_repo)
        self.assertTrue(lock_res["ok"])
        self.assertEqual(lock_res["push_url"], READONLY_PUSH_SENTINEL)

        verify_res = verify_readonly_mirror(self.mirror_repo)
        self.assertTrue(verify_res["compliant"])

        # Attempting to push must fail physically
        push_attempt = subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=str(self.mirror_repo),
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(push_attempt.returncode, 0)

    def test_sync_fetches_remote_and_discards_local_drift(self) -> None:
        # Advance remote
        (self.seed_repo / "README.md").write_text("v2\n", encoding="utf-8")
        _git(self.seed_repo, "add", "README.md")
        _git(self.seed_repo, "commit", "-m", "v2")
        _git(self.seed_repo, "push", "origin", "main")

        # Introduce unauthorized local edit in mirror
        (self.mirror_repo / "README.md").write_text("unauthorized local edit\n", encoding="utf-8")

        sync_res = sync_readonly_mirror(self.mirror_repo, branch="main")
        self.assertTrue(sync_res["ok"])
        self.assertTrue(sync_res["push_locked"])
        self.assertEqual((self.mirror_repo / "README.md").read_text(encoding="utf-8"), "v2\n")

        verify_res = verify_readonly_mirror(self.mirror_repo)
        self.assertTrue(verify_res["compliant"])


if __name__ == "__main__":
    unittest.main()
