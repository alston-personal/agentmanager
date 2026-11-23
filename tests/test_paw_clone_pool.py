"""Tests for agent_core.paw_clone_pool (PAW-CLONE-01..03)."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from agent_core.atlas_inbox import consolidate_atlas_inbox
from agent_core.paw_clone_pool import (
    PawClonePool,
    PawCloneTask,
    PoolCapacityExceededError,
    TaskAlreadyClaimedError,
)


def _init_temp_git_repo(repo_dir: Path) -> None:
    repo_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "paw-test@agentos.local"],
        cwd=str(repo_dir),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Paw Test"],
        cwd=str(repo_dir),
        check=True,
        capture_output=True,
    )
    (repo_dir / "README.md").write_text("# Test Repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=str(repo_dir),
        check=True,
        capture_output=True,
    )


class TestPawClonePool(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.repo = self.base / "repo"
        self.pool_root = self.base / "pool"
        self.data_root = self.base / "agent-data"
        _init_temp_git_repo(self.repo)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_parallel_clones_isolated_worktrees_and_atlas_inbox_return(self) -> None:
        pool = PawClonePool(self.repo, self.pool_root, data_root=self.data_root, max_clones=3)
        tasks = [
            PawCloneTask(task_id="PE-01", project="persona-engine", title="Setup persona-engine"),
            PawCloneTask(task_id="ZW-REV-01", project="zeus-writer", title="Review queue contract"),
        ]

        def worker(handle, task):
            target = handle.worktree_path / f"{task.task_id}.txt"
            target.write_text(f"done by {handle.clone_id}\n", encoding="utf-8")
            self.assertTrue(target.exists())
            return {"status": "completed", "summary": f"Implemented {task.task_id}"}

        results = pool.run_parallel(tasks, worker, cleanup_branch=True)
        self.assertEqual(len(results), 2)
        for res in results:
            self.assertEqual(res.status, "completed")
            self.assertTrue(res.cleaned_up)
            self.assertTrue(res.experience_card_path)
            self.assertTrue(Path(res.experience_card_path).exists())

        # Main repo must remain untouched by isolated worktree writes.
        self.assertFalse((self.repo / "PE-01.txt").exists())
        self.assertFalse((self.repo / "ZW-REV-01.txt").exists())
        self.assertEqual(pool.active_clones(), [])
        self.assertEqual(list(pool.locks_dir.glob("*.lock")), [])

        # Atlas inbox consolidation should see both returned cards.
        summary = consolidate_atlas_inbox(self.data_root)
        self.assertEqual(summary["processed"], 2)
        self.assertEqual(summary["promoted_growth"], 2)

    def test_duplicate_claim_and_capacity_enforcement(self) -> None:
        pool = PawClonePool(self.repo, self.pool_root, max_clones=1)
        t1 = PawCloneTask(task_id="ML-01", project="persona-market-learner", title="Init market learner")
        handle = pool.spawn_clone(t1)
        try:
            with self.assertRaises(PoolCapacityExceededError):
                pool.spawn_clone(
                    PawCloneTask(task_id="ML-02", project="persona-market-learner", title="Fetch data")
                )

            # Increase capacity to verify duplicate lock check independently.
            pool.max_clones = 2
            with self.assertRaises(TaskAlreadyClaimedError):
                pool.spawn_clone(t1)
        finally:
            res = pool.complete_clone(handle, status="completed", summary="Done", cleanup_branch=True)
            self.assertTrue(res.cleaned_up)

    def test_failure_releases_lock_and_allows_retry(self) -> None:
        pool = PawClonePool(self.repo, self.pool_root, data_root=self.data_root, max_clones=2)
        task = PawCloneTask(task_id="RETRY-01", project="agentmanager", title="Flaky task")

        def failing_worker(_handle, _task):
            raise RuntimeError("transient build error")

        results = pool.run_parallel([task], failing_worker, cleanup_branch=True)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "failed")
        self.assertIn("transient build error", results[0].error)
        self.assertTrue(results[0].cleaned_up)
        self.assertEqual(list(pool.locks_dir.glob("*.lock")), [])

        # Lock was released, so a retry must succeed.
        retry_results = pool.run_parallel(
            [task],
            lambda _h, _t: {"status": "completed", "summary": "Succeeded on retry"},
            cleanup_branch=True,
        )
        self.assertEqual(retry_results[0].status, "completed")
        self.assertTrue(retry_results[0].cleaned_up)


if __name__ == "__main__":
    unittest.main()
