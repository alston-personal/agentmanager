from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

EXPECTED_HEAD = "43d3edbbb4ab8b0e883c04e5297c8aaa724cbd4c"
SOURCE_REF = "core/integration"
EXPECTED_PATHS = {
    "agent_core/controller_api.py",
    "agent_core/controller_service.py",
    "agent_core/realm_server.py",
    "agentos_node/bootstrap_control.py",
    "agentos_node/bootstrap_scheduler.py",
    "agentos_node/gemini_web_bridge.py",
    "agentos_node/web_agent_surface.py",
    "dashboard/app/api/agentos/[...path]/route.ts",
    "scripts/mio_persona_social_loop_user.py",
    "scripts/threads_web_dm_bridge_user.py",
    "scripts/update_scheduler_board.py",
}



def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit("git verification failed: " + " ".join(args[:2]))
    return proc.stdout.strip()


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: recover_known_git_dirty_checkout.py <repo-root>")
    root = Path(sys.argv[1]).resolve()
    if not (root / ".git").exists():
        raise SystemExit("repository unavailable")

    head = git(root, "rev-parse", "HEAD")
    if head != EXPECTED_HEAD:
        raise SystemExit(f"unexpected Oracle checkout HEAD: {head}")

    raw = subprocess.check_output(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=no"],
        cwd=root,
        text=False,
    )
    entries: list[tuple[str, str]] = []
    for item in raw.split(b"\0"):
        if not item:
            continue
        text = item.decode("utf-8")
        if len(text) < 4:
            raise SystemExit("invalid git status record")
        entries.append((text[:2], text[3:]))

    actual_paths = {rel for _, rel in entries}
    if actual_paths != EXPECTED_PATHS:
        raise SystemExit(
            "dirty path set changed; refusing recovery: "
            + json.dumps(sorted(actual_paths), ensure_ascii=False)
        )
    if any(status != " M" for status, _ in entries):
        raise SystemExit("dirty status is not ordinary unstaged modification; refusing recovery")

    fetch = subprocess.run(
        ["git", "fetch", "--no-tags", "origin", SOURCE_REF],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if fetch.returncode != 0:
        raise SystemExit("unable to refresh bounded source ref")
    target_tip = git(root, "rev-parse", "FETCH_HEAD")
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", EXPECTED_HEAD, target_tip],
        cwd=root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if ancestry.returncode != 0:
        raise SystemExit("core/integration no longer descends from the observed Oracle HEAD")

    evidence = []
    for rel in sorted(EXPECTED_PATHS):
        path = root / rel
        if path.is_symlink() or not path.is_file():
            raise SystemExit(f"dirty path is not a regular file: {rel}")
        worktree_blob = git(root, "hash-object", "--", rel)
        provenance_commit = ""
        proc = subprocess.run(
            ["git", "log", "--format=%H", target_tip, "--", rel],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if proc.returncode != 0:
            raise SystemExit(f"unable to inspect Git provenance: {rel}")
        for commit in proc.stdout.splitlines():
            if not commit:
                continue
            blob_proc = subprocess.run(
                ["git", "rev-parse", f"{commit}:{rel}"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            if blob_proc.returncode == 0 and blob_proc.stdout.strip() == worktree_blob:
                provenance_commit = commit
                break
        if not provenance_commit:
            raise SystemExit(f"dirty blob has no core/integration Git provenance: {rel}")
        evidence.append(
            {
                "path": rel,
                "status": " M",
                "worktree_blob": worktree_blob,
                "provenance_commit": provenance_commit,
                "source_ref": SOURCE_REF,
                "source_tip": target_tip,
                "head_blob": git(root, "rev-parse", f"HEAD:{rel}"),
                "content_exposed": False,
            }
        )

    data_root = Path(
        os.environ.get("AGENT_DATA_ROOT")
        or os.environ.get("AGENT_DATA_DIR")
        or (Path.home() / "agent-data")
    )
    receipt_dir = data_root / "runtime" / "backups" / "checkout-drift"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt = receipt_dir / "known-git-recovery-20261006.json"
    payload = {
        "schema": "agentos.known-git-checkout-recovery/v1",
        "repository": "alston-personal/agentmanager",
        "observed_head": head,
        "classification": "ALL_DIRTY_CONTENT_GIT_PROVENANCED",
        "recovery": "pending",
        "paths": evidence,
        "content_exposed": False,
        "credential_exposed": False,
    }
    tmp = receipt.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, receipt)

    subprocess.run(
        ["git", "checkout", "HEAD", "--", *sorted(EXPECTED_PATHS)],
        cwd=root,
        check=True,
    )
    after = git(root, "status", "--porcelain=v1", "--untracked-files=no")
    if after:
        raise SystemExit("tracked checkout still dirty after bounded recovery")

    payload["recovery"] = "completed"
    payload["recovered_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    tmp.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, receipt)
    print("oracle_core_known_git_dirty_recovery=PASS")
    print("oracle_core_recovered_head=" + head)
    print("oracle_core_recovered_path_count=" + str(len(EXPECTED_PATHS)))
    print("oracle_core_provenance_source_ref=" + SOURCE_REF)
    print("oracle_core_provenance_source_tip=" + target_tip)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
