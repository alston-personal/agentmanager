"""Paw Clone Pool: isolated git-worktree parallel execution for HephaestusPawWorker.

Implements PAW-CLONE-01 & PAW-CLONE-02:
- Atomic file-based task locking (O_CREAT | O_EXCL) to prevent duplicate claims.
- Dynamic isolated git worktree spawning per task (paw-clone-<n>-<task_id>).
- Safe concurrent execution via ThreadPoolExecutor bounded by max_clones.
- Experience return to Atlas shadow-clone inbox (agent_core.atlas_inbox) and
  automatic worktree + lock cleanup on both success and failure.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from agent_core.atlas_inbox import submit_experience_card


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_slug(raw: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", raw.strip()).strip("-.")
    return slug or "task"


class PawClonePoolError(RuntimeError):
    """Base error for PawClonePool operations."""


class TaskAlreadyClaimedError(PawClonePoolError):
    """Raised when a task is already locked by another active Paw clone."""


class PoolCapacityExceededError(PawClonePoolError):
    """Raised when active clones reach max_clones."""


@dataclass(frozen=True)
class PawCloneTask:
    task_id: str
    project: str
    title: str
    branch_name: str = ""
    base_ref: str = "HEAD"

    def resolved_branch(self) -> str:
        if self.branch_name.strip():
            return self.branch_name.strip()
        return f"paw/{_sanitize_slug(self.task_id).lower()}"


@dataclass(frozen=True)
class PawCloneHandle:
    clone_id: str
    task_id: str
    project: str
    worktree_path: Path
    branch_name: str
    lock_path: Path
    created_at: str


@dataclass(frozen=True)
class PawCloneResult:
    clone_id: str
    task_id: str
    status: str
    summary: str
    pr_url: str = ""
    error: str = ""
    experience_card_path: str = ""
    cleaned_up: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class PawClonePool:
    """Manages isolated git worktree clones for parallel Paw task execution."""

    def __init__(
        self,
        repo_root: Path,
        pool_root: Path,
        *,
        data_root: Path | None = None,
        max_clones: int = 4,
    ) -> None:
        if max_clones < 1:
            raise ValueError("max_clones must be >= 1")
        self.repo_root = Path(repo_root).resolve()
        self.pool_root = Path(pool_root).resolve()
        self.data_root = Path(data_root).resolve() if data_root is not None else None
        self.max_clones = max_clones

        self.locks_dir = self.pool_root / "locks"
        self.worktrees_dir = self.pool_root / "worktrees"
        self.locks_dir.mkdir(parents=True, exist_ok=True)
        self.worktrees_dir.mkdir(parents=True, exist_ok=True)

        self._mu = threading.Lock()
        self._active: dict[str, PawCloneHandle] = {}
        self._counter = 0

    def _run_git(self, args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd or self.repo_root),
            capture_output=True,
            text=True,
            check=False,
        )

    def _acquire_lock(self, task_id: str, clone_id: str) -> Path:
        safe_id = _sanitize_slug(task_id)
        lock_path = self.locks_dir / f"{safe_id}.lock"
        payload = json.dumps(
            {
                "task_id": task_id,
                "clone_id": clone_id,
                "pid": os.getpid(),
                "claimed_at": _utc_now_iso(),
            },
            ensure_ascii=False,
        )
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError as exc:
            raise TaskAlreadyClaimedError(f"Task '{task_id}' is already claimed ({lock_path})") from exc
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        return lock_path

    def _release_lock(self, lock_path: Path) -> None:
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass

    def active_clones(self) -> list[PawCloneHandle]:
        with self._mu:
            return list(self._active.values())

    def spawn_clone(self, task: PawCloneTask) -> PawCloneHandle:
        """Atomically claim a task and spawn an isolated git worktree clone."""
        with self._mu:
            if len(self._active) >= self.max_clones:
                raise PoolCapacityExceededError(
                    f"PawClonePool at capacity ({len(self._active)}/{self.max_clones})"
                )
            self._counter += 1
            seq = self._counter
            safe_id = _sanitize_slug(task.task_id)
            clone_id = f"paw-clone-{seq}-{safe_id}"
            lock_path = self._acquire_lock(task.task_id, clone_id)

            branch_name = task.resolved_branch()
            worktree_path = self.worktrees_dir / clone_id
            handle = PawCloneHandle(
                clone_id=clone_id,
                task_id=task.task_id,
                project=task.project,
                worktree_path=worktree_path,
                branch_name=branch_name,
                lock_path=lock_path,
                created_at=_utc_now_iso(),
            )
            self._active[clone_id] = handle

        # Create git worktree outside the in-memory lock; on failure, roll back lock & active slot.
        proc = self._run_git(
            ["worktree", "add", "-b", branch_name, str(worktree_path), task.base_ref]
        )
        if proc.returncode != 0:
            with self._mu:
                self._active.pop(clone_id, None)
            self._release_lock(lock_path)
            raise PawClonePoolError(
                f"Failed to spawn git worktree for {clone_id}: {proc.stderr.strip() or proc.stdout.strip()}"
            )

        return handle

    def complete_clone(
        self,
        handle: PawCloneHandle,
        *,
        status: str,
        summary: str,
        pr_url: str = "",
        error: str = "",
        cleanup_branch: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> PawCloneResult:
        """Report completion, return experience to Atlas inbox, and clean up worktree & lock."""
        exp_path_str = ""
        if self.data_root is not None:
            try:
                card_path = submit_experience_card(
                    data_root=self.data_root,
                    kind="pitfall" if status == "failed" else "growth_observation",
                    title=f"[{handle.project}] {handle.task_id} ({handle.clone_id})",
                    summary=error if error else summary,
                    source_surface="paw-clone-pool",
                    evidence_refs=[pr_url] if pr_url else [],
                )
                exp_path_str = str(card_path)
            except Exception:
                exp_path_str = ""

        cleaned_up = False
        try:
            rm_proc = self._run_git(["worktree", "remove", "--force", str(handle.worktree_path)])
            if rm_proc.returncode != 0 and handle.worktree_path.exists():
                shutil.rmtree(handle.worktree_path, ignore_errors=True)
                self._run_git(["worktree", "prune"])
            if cleanup_branch:
                self._run_git(["branch", "-D", handle.branch_name])
            cleaned_up = not handle.worktree_path.exists()
        finally:
            with self._mu:
                self._active.pop(handle.clone_id, None)
            self._release_lock(handle.lock_path)

        return PawCloneResult(
            clone_id=handle.clone_id,
            task_id=handle.task_id,
            status=status,
            summary=summary,
            pr_url=pr_url,
            error=error,
            experience_card_path=exp_path_str,
            cleaned_up=cleaned_up,
            metadata=dict(metadata or {}),
        )

    def run_parallel(
        self,
        tasks: list[PawCloneTask],
        worker_fn: Callable[[PawCloneHandle, PawCloneTask], dict[str, Any]],
        *,
        cleanup_branch: bool = False,
    ) -> list[PawCloneResult]:
        """Spawn isolated clones in parallel, execute worker_fn, and guarantee cleanup."""
        results: list[PawCloneResult] = []

        def _execute_one(task: PawCloneTask) -> PawCloneResult:
            handle = self.spawn_clone(task)
            try:
                out = worker_fn(handle, task) or {}
                return self.complete_clone(
                    handle,
                    status=str(out.get("status") or "completed"),
                    summary=str(out.get("summary") or f"Completed {task.task_id}"),
                    pr_url=str(out.get("pr_url") or ""),
                    error=str(out.get("error") or ""),
                    cleanup_branch=cleanup_branch,
                    metadata=out,
                )
            except Exception as exc:
                return self.complete_clone(
                    handle,
                    status="failed",
                    summary=f"Failed {task.task_id}",
                    error=str(exc),
                    cleanup_branch=cleanup_branch,
                )

        with ThreadPoolExecutor(max_workers=self.max_clones) as executor:
            future_map = {executor.submit(_execute_one, t): t for t in tasks}
            for fut in as_completed(future_map):
                results.append(fut.result())

        return results
