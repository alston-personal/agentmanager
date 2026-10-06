from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

EXPECTED_HEAD = "43d3edbbb4ab8b0e883c04e5297c8aaa724cbd4c"
EXPECTED = {
    "agent_core/controller_api.py": ("1892f5b359fdb33716637f71b06af64c59caca4d", "396a6f7b6aa07eef5942445233ca1bbe2a7af850"),
    "agent_core/controller_service.py": ("88a27f37f4cf43dfa5500bcef6ec9e2de50c389e", "396a6f7b6aa07eef5942445233ca1bbe2a7af850"),
    "agent_core/realm_server.py": ("58543d49e5e13e7ed14bf215b7f1ea67503505a5", "e11ee57d4776a4b0fd79a6a32f19d0268da9645e"),
    "agentos_node/bootstrap_control.py": ("3dc50809d685a1def799e53ef209c53272045545", "396a6f7b6aa07eef5942445233ca1bbe2a7af850"),
    "agentos_node/bootstrap_scheduler.py": ("fac71d4ac3f39515d85f56c32327ffc6eac2cf97", "396a6f7b6aa07eef5942445233ca1bbe2a7af850"),
    "agentos_node/gemini_web_bridge.py": ("c7737d79c11af93e52fa179a3f7b1800c0387f9f", "396a6f7b6aa07eef5942445233ca1bbe2a7af850"),
    "agentos_node/web_agent_surface.py": ("1f138724bf80c689c15d675e1c22fbce595200cd", "396a6f7b6aa07eef5942445233ca1bbe2a7af850"),
    "dashboard/app/api/agentos/[...path]/route.ts": ("70a6c2eed1baf14550f26b99adfe15325f9281c4", "396a6f7b6aa07eef5942445233ca1bbe2a7af850"),
    "scripts/mio_persona_social_loop_user.py": ("b64b3ee5a8b8d380a9b5b0202d1e5d3a28e30a7b", "396a6f7b6aa07eef5942445233ca1bbe2a7af850"),
    "scripts/threads_web_dm_bridge_user.py": ("32e9390ec8edb65089b2e53053adfff02f12fd9d", "396a6f7b6aa07eef5942445233ca1bbe2a7af850"),
    "scripts/update_scheduler_board.py": ("53b9eef5a72a2e66b39e4f2046947946adf06dd8", "2636f4c0583c7110a9a15d17e0c287bc08607655"),
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
    if actual_paths != set(EXPECTED):
        raise SystemExit(
            "dirty path set changed; refusing recovery: "
            + json.dumps(sorted(actual_paths), ensure_ascii=False)
        )
    if any(status != " M" for status, _ in entries):
        raise SystemExit("dirty status is not ordinary unstaged modification; refusing recovery")

    evidence = []
    for rel, (expected_blob, provenance_commit) in EXPECTED.items():
        path = root / rel
        if path.is_symlink() or not path.is_file():
            raise SystemExit(f"dirty path is not a regular file: {rel}")
        worktree_blob = git(root, "hash-object", "--", rel)
        if worktree_blob != expected_blob:
            raise SystemExit(f"dirty blob changed; refusing recovery: {rel}")
        provenance_blob = git(root, "rev-parse", f"{provenance_commit}:{rel}")
        if provenance_blob != worktree_blob:
            raise SystemExit(f"Git provenance mismatch; refusing recovery: {rel}")
        evidence.append(
            {
                "path": rel,
                "status": " M",
                "worktree_blob": worktree_blob,
                "provenance_commit": provenance_commit,
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
        ["git", "checkout", "HEAD", "--", *EXPECTED.keys()],
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
    print("oracle_core_recovered_path_count=" + str(len(EXPECTED)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
