#!/usr/bin/env python3
"""Read-only preflight for a governed LeopardCat backend release.

No checkout, restart, or file mutation. Designed to fail closed before any
future exact-SHA release adapter is permitted to touch production.
"""
import argparse
import json
import re
import subprocess
import urllib.request
from pathlib import Path

SHA = re.compile(r"^[0-9a-f]{40}$")
SERVICE = "leopardcat-tarot.service"
ROOT = Path("/home/ubuntu/leopardcat-tarot")
APP = ROOT / "website"
ALLOW_DIRTY = {"website/stats.json", "website/dist/index.html"}
ALLOW_PREFIX = ("website/node_modules/.vite/", ".claude/")


def command(*args):
    p = subprocess.run(args, text=True, capture_output=True, timeout=15)
    if p.returncode:
        raise RuntimeError("preflight_command_failed:" + args[0])
    return p.stdout.strip()


def inspect(target):
    if not SHA.fullmatch(target):
        raise ValueError("target_sha_not_exact")
    cwd = command("systemctl", "--user", "show", SERVICE, "-p", "WorkingDirectory", "--value")
    if cwd != str(APP):
        raise RuntimeError("unexpected_service_working_directory")
    if command("systemctl", "--user", "is-active", SERVICE) != "active":
        raise RuntimeError("service_not_active")
    remote = command("git", "-C", str(ROOT), "remote", "get-url", "origin")
    if remote != "https://github.com/alston-personal/leopardcat-tarot.git":
        raise RuntimeError("unexpected_source_origin")
    head = command("git", "-C", str(ROOT), "rev-parse", "HEAD")
    branch = command("git", "-C", str(ROOT), "branch", "--show-current")
    if branch != "main":
        raise RuntimeError("runtime_not_on_main")
    dirty = [line[3:] for line in command("git", "-C", str(ROOT), "status", "--porcelain").splitlines()]
    unexpected = [p for p in dirty if p not in ALLOW_DIRTY and not any(p.startswith(x) for x in ALLOW_PREFIX)]
    if unexpected:
        raise RuntimeError("unexpected_runtime_dirty_paths")
    # Fetch and verify the target through the existing trusted product remote.
    command("git", "-C", str(ROOT), "fetch", "--no-tags", "origin", "main")
    # GitHub's target must be present in the fetched repository.
    ancestor = subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", head, target], timeout=15)
    if ancestor.returncode:
        raise RuntimeError("target_not_fast_forward_from_runtime")
    # Reject non-main target commits: a product request cannot deploy an arbitrary fork.
    release_tip = command("git", "-C", str(ROOT), "rev-parse", "refs/remotes/origin/main")
    if subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", target, release_tip], timeout=15).returncode:
        raise RuntimeError("target_not_on_main_release_lane")
    with urllib.request.urlopen("http://127.0.0.1:8088/api/v1/personas?deck=leopardcat", timeout=8) as res:
        if res.status != 200:
            raise RuntimeError("baseline_persona_api_unhealthy")
    return {"status": "preflight_pass", "runtime_head": head, "target_sha": target, "service": SERVICE,
            "mutation_performed": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-sha", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.target_sha), sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc).split(":")[0], "mutation_performed": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
