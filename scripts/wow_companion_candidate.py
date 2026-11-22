#!/usr/bin/env python3
"""Stage and checksum-lock the existing first-party WoW AgentOS AddOn candidate.

This deliberately excludes missing Nav Assist and all third-party AddOns.
It never installs files or sends credentials to the game client.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from scripts.wow_companion_package import BundleError, build_bundle

ADDONS = ("AgentOSWoW", "AgentOSWoW_R001")
ROOT = Path(__file__).resolve().parents[1]


def _git(*args: str) -> str:
    cmd = subprocess.run(["git", "-C", str(ROOT), *args], text=True,
                         capture_output=True, check=False)
    if cmd.returncode:
        raise BundleError("repository source provenance unavailable")
    return cmd.stdout.strip()


def build_candidate(output: Path, stage_root: Path, expected_commit: str) -> dict:
    actual = _git("rev-parse", "HEAD")
    if actual != expected_commit:
        raise BundleError("git HEAD does not match the expected exact source commit")
    if stage_root.resolve() == ROOT.resolve():
        raise BundleError("stage root must be separate from source repository")
    stage_root.mkdir(parents=True, exist_ok=True)
    tracked = set(_git("ls-tree", "-r", "--name-only", "HEAD", "--", "integrations/wow/").splitlines())
    lock_entries = []
    for addon in ADDONS:
        source_prefix = f"integrations/wow/{addon}/"
        names = sorted(path for path in tracked if path.startswith(source_prefix))
        if not names:
            raise BundleError(f"missing source files for {addon}")
        target_dir = stage_root / addon
        target_dir.mkdir(parents=True, exist_ok=True)
        for full_path in names:
            rel = full_path[len(source_prefix):]
            if not rel or Path(rel).is_absolute() or ".." in Path(rel).parts:
                raise BundleError("unsafe tracked path")
            original = ROOT / full_path
            if original.is_symlink() or not original.is_file():
                raise BundleError("source is missing or symlink")
            actual_blob = original.read_bytes()
            committed_blob = subprocess.run(
                ["git", "-C", str(ROOT), "show", f"HEAD:{full_path}"],
                capture_output=True, check=False,
            )
            if committed_blob.returncode or committed_blob.stdout != actual_blob:
                raise BundleError(f"source not identical to pinned git commit: {full_path}")
            dest = target_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(actual_blob)
            lock_entries.append({
                "addon": addon, "path": rel,
                "sha256": hashlib.sha256(actual_blob).hexdigest(),
            })
    lock = stage_root / "source-lock.json"
    lock.write_text(json.dumps({
        "schema": "agentos.wow-suite-source-lock/v1",
        "files": lock_entries
    }, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    package = build_bundle(lock, stage_root, output)
    package.update({
        "source_commit": actual,
        "candidate_only": True,
        "complete_companion_suite": False,
        "nav_assist_included": False,
        "game_client_accepted": False,
        "release_approved": False,
    })
    return package


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--expected-commit", required=True)
    p.add_argument("--stage-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    try:
        result = build_candidate(args.output, args.stage_root, args.expected_commit)
    except (BundleError, OSError, ValueError, KeyError) as e:
        p.exit(2, f"WoW AddOn candidate packaging refused: {e}\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
