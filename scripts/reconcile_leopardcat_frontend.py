#!/usr/bin/env python3
"""Governed, frontend-only LeopardCat production reconcile for Core #288.

The product owns only the exact source SHA intent. Core owns repository path,
release lane, runtime user, build/swap procedure, public origin, and rollback policy.
No request-controlled shell, executable, argv, path, or secret is accepted.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from run_governed_execution_request import (
    git_state,
    inspect_leopardcat_parity,
    load_json,
    resolve_authority,
)

PROJECT_ID = "leopardcat-tarot"
CAPABILITY_ID = "leopardcat.production.frontend.reconcile"


def now():
    return datetime.now(timezone.utc).isoformat()


def fail(message):
    raise RuntimeError(message)


def run(argv, *, cwd=None):
    return subprocess.run(argv, cwd=cwd, text=True, capture_output=True, check=False)


def as_user(user, argv, *, cwd=None):
    fixed = ["sudo", "-n", "-u", user, "--", *argv]
    return run(fixed, cwd=cwd)


def require(proc, label):
    if proc.returncode:
        # Never echo command output from privileged git/build operations: remotes or
        # package-manager diagnostics may contain environment-specific information.
        fail(f"{label} failed")
    return proc


def path_allowed(path, exact, prefixes):
    return path in exact or any(path.startswith(prefix) for prefix in prefixes)


def fetch_request(project, registry):
    source = project["request_source"]
    repo_root = source["repo_root"]
    source_ref = source["source_ref"]
    user = source.get("execution_user") or "ubuntu"
    request_path = project.get("reconcile_request_path")
    if not request_path or request_path.startswith("/") or ".." in Path(request_path).parts:
        fail("invalid registry-owned reconcile request path")
    require(as_user(user, ["git", "-c", f"safe.directory={repo_root}", "-C", repo_root,
                           "fetch", "--depth=64", "origin", source_ref]), "product request fetch")
    shown = require(as_user(user, ["git", "-c", f"safe.directory={repo_root}", "-C", repo_root,
                                    "show", f"FETCH_HEAD:{request_path}"]), "product request read")
    try:
        request = json.loads(shown.stdout)
    except json.JSONDecodeError:
        fail("product reconcile request is not valid JSON")
    _, capability = resolve_authority(request, registry)
    if request["project_id"] != PROJECT_ID or request["capability"] != CAPABILITY_ID:
        fail("unexpected reconcile project/capability")
    return request, capability, user


def git_user(user, repo_root, *args):
    return as_user(user, ["git", "-c", f"safe.directory={repo_root}", "-C", repo_root, *args])


def capture_file(user, path, backup):
    if not path.exists():
        return False
    require(as_user(user, ["cp", "--", str(path), str(backup)]), "preserve runtime file")
    return True


def restore_file(user, backup, path, existed):
    if existed:
        require(as_user(user, ["cp", "--", str(backup), str(path)]), "restore runtime file")


def main():
    registry_path = sys.argv[1] if len(sys.argv) > 1 else "governance/execution-authority.json"
    receipt_path = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/leopardcat-production-reconcile-receipt.json")
    receipt = {
        "schema": "agentos.execution-receipt/v1",
        "request_id": None,
        "project_id": PROJECT_ID,
        "repository": None,
        "environment": "production",
        "source_ref": None,
        "source_sha": None,
        "capability": CAPABILITY_ID,
        "result_status": "failed",
        "evidence_level": None,
        "artifact_digest": None,
        "executor_identity": os.environ.get("RUNNER_NAME") or os.uname().nodename,
        "started_at": now(),
        "completed_at": None,
        "evidence": {},
        "error": None,
    }
    old_head = None
    source_switched = False
    dist_swapped = False
    old_dist = None
    new_dist = None
    preserve = []
    try:
        registry = load_json(registry_path)
        project = registry["projects"][PROJECT_ID]
        request, capability, user = fetch_request(project, registry)
        runtime = capability["runtime"]
        repo_root = runtime["repo_root"]
        public_origin = runtime["public_origin"]
        build_root = Path(repo_root) / runtime["build_root"]
        dist_path = Path(repo_root) / runtime["dist_path"]
        receipt.update({
            "request_id": request["request_id"],
            "repository": request["repository"],
            "source_ref": request["source_ref"],
            "source_sha": request["source_sha"],
        })

        pre = git_state(repo_root,
            allowed_dirty_exact=runtime.get("allowed_dirty_exact", ()),
            allowed_dirty_prefixes=runtime.get("allowed_dirty_prefixes", ()))
        if pre["unexpected_dirty_paths"]:
            fail("unexpected production dirty state")
        old_head = pre["head"]

        # The desired SHA must be contained by the registry-owned release lane fetched above.
        contain = git_user(user, repo_root, "merge-base", "--is-ancestor", request["source_sha"], "FETCH_HEAD")
        if contain.returncode:
            fail("requested source SHA is outside fetched main release lane")

        changed = require(git_user(user, repo_root, "diff", "--name-only", f"{old_head}..{request['source_sha']}"),
                          "changed-path inspection").stdout.splitlines()
        exact = runtime.get("allowed_changed_exact", [])
        prefixes = runtime.get("allowed_changed_prefixes", [])
        rejected = [p for p in changed if p and not path_allowed(p, exact, prefixes)]
        if rejected:
            fail("requested release contains changes outside frontend-only authority")

        tmp = Path(tempfile.mkdtemp(prefix="lc-reconcile-"))
        new_dist = tmp / "new-dist"
        old_dist = tmp / "old-dist"
        for rel in runtime.get("preserve_paths", []):
            src = Path(repo_root) / rel
            backup = tmp / (Path(rel).name + ".preserved")
            preserve.append((src, backup, capture_file(user, src, backup)))

        if old_head != request["source_sha"]:
            require(git_user(user, repo_root, "reset", "--hard", request["source_sha"]), "source reconcile")
            source_switched = True
            for src, backup, existed in preserve:
                restore_file(user, backup, src, existed)

        # Build to a separate directory first; production dist is untouched until build success.
        require(as_user(user, ["npm", "ci"], cwd=str(build_root)), "npm ci")
        require(as_user(user, ["npx", "vite", "build", "--outDir", str(new_dist), "--emptyOutDir"],
                        cwd=str(build_root)), "frontend build")
        if not (new_dist / "index.html").is_file():
            fail("frontend build produced no index.html")

        if dist_path.exists():
            require(as_user(user, ["mv", "--", str(dist_path), str(old_dist)]), "stage old dist")
        require(as_user(user, ["mv", "--", str(new_dist), str(dist_path)]), "activate new dist")
        dist_swapped = True

        evidence, digest, accepted, level = inspect_leopardcat_parity(request, capability)
        if not accepted:
            fail("post-reconcile production parity mismatch")
        receipt["evidence"] = {
            "mutation": "frontend-only transactional reconcile",
            "previous_runtime_head": old_head,
            "changed_paths": changed,
            "rollback_available_during_execution": True,
            **evidence,
        }
        receipt["artifact_digest"] = digest
        receipt["evidence_level"] = level + "+governed_mutation"
        receipt["result_status"] = "success"
        if old_dist and old_dist.exists():
            shutil.rmtree(old_dist, ignore_errors=True)
    except Exception as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        # Best-effort rollback. Do not mask the original failure with rollback output.
        try:
            if dist_swapped and old_dist and old_dist.exists():
                current_dist = Path(registry["capabilities"][CAPABILITY_ID]["runtime"]["repo_root"]) / \
                    registry["capabilities"][CAPABILITY_ID]["runtime"]["dist_path"]
                failed_dist = old_dist.parent / "failed-dist"
                as_user(user, ["mv", "--", str(current_dist), str(failed_dist)])
                as_user(user, ["mv", "--", str(old_dist), str(current_dist)])
            if source_switched and old_head:
                repo_root = registry["capabilities"][CAPABILITY_ID]["runtime"]["repo_root"]
                git_user(user, repo_root, "reset", "--hard", old_head)
                for src, backup, existed in preserve:
                    restore_file(user, backup, src, existed)
        except Exception:
            pass
    finally:
        receipt["completed_at"] = now()
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["result_status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
