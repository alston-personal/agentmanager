#!/usr/bin/env python3
"""Fetch a product-owned execution request through its Oracle-local repository.

This solves the private-repository boundary without copying a cross-repository GitHub
credential into Core workflows. Core accepts only a project id; repository root,
source ref, and request path come from the execution authority registry. The fetch
updates Git metadata only and never checks out or mutates the production working tree.
"""
import json
import subprocess
import sys
from pathlib import Path

from run_governed_execution_request import load_json, resolve_authority


def fail(message):
    raise RuntimeError(message)


def run_git(repo_root, *args):
    return subprocess.run(
        ["git", "-C", repo_root, *args],
        text=True,
        capture_output=True,
        check=False,
    )


def fetch_product_request(project_id, registry):
    project = registry.get("projects", {}).get(project_id)
    if not project:
        fail("project is not allowlisted")
    source = project.get("request_source") or {}
    repo_root = source.get("repo_root")
    source_ref = source.get("source_ref")
    request_path = project.get("request_path")
    if not all(isinstance(value, str) and value for value in (repo_root, source_ref, request_path)):
        fail("project request source is incomplete")
    if source_ref not in project.get("allowed_source_refs", []):
        fail("request source ref is outside release-lane authority")
    if request_path.startswith("/") or ".." in Path(request_path).parts:
        fail("request path is outside repository authority")

    fetch = run_git(repo_root, "fetch", "--depth=1", "origin", source_ref)
    if fetch.returncode:
        # Do not echo git stderr/stdout: a misconfigured remote may contain credentials.
        fail("product repository fetch failed")
    show = run_git(repo_root, "show", f"FETCH_HEAD:{request_path}")
    if show.returncode:
        fail("product request is missing at the governed path")
    try:
        request = json.loads(show.stdout)
    except json.JSONDecodeError:
        fail("product request is not valid JSON")

    resolved_project, _ = resolve_authority(request, registry)
    if request.get("project_id") != project_id:
        fail("product request project identity mismatch")
    if request.get("source_ref") != source_ref:
        fail("product request release lane mismatch")
    if resolved_project is not project:
        fail("resolved project authority mismatch")
    return request, source_ref, request_path


def main():
    if len(sys.argv) not in (3, 4):
        print("usage: fetch_governed_product_request.py PROJECT_ID OUTPUT [REGISTRY]", file=sys.stderr)
        return 2
    project_id = sys.argv[1]
    output = Path(sys.argv[2])
    registry_path = sys.argv[3] if len(sys.argv) == 4 else "governance/execution-authority.json"
    try:
        registry = load_json(registry_path)
        request, source_ref, request_path = fetch_product_request(project_id, registry)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({
            "status": "success",
            "project_id": project_id,
            "source_ref": source_ref,
            "request_path": request_path,
            "request_id": request.get("request_id"),
            "source_sha": request.get("source_sha"),
            "capability": request.get("capability"),
        }, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({
            "status": "failed",
            "project_id": project_id,
            "error": f"{type(exc).__name__}: {exc}",
        }, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
