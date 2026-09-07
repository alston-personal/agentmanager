#!/usr/bin/env python3
"""Run Core #288 reconcile under the already-enrolled Oracle runner identity.

LeopardCat's runtime repository is readable/writable by the enrolled AgentOS runner
boundary; unlike Vendor, it does not require or authorize a sudo user transition.
The request is fetched from the registry-owned canonical public repository URL rather
than trusting a mutable local remote configuration.
"""
import json
from pathlib import Path

import reconcile_leopardcat_frontend as reconcile


def direct_identity(_user, argv, *, cwd=None):
    return reconcile.run(argv, cwd=cwd)


def fetch_request_from_canonical_origin(project, registry):
    source = project["request_source"]
    repo_root = source["repo_root"]
    source_ref = source["source_ref"]
    request_path = project.get("reconcile_request_path")
    if not request_path or request_path.startswith("/") or ".." in Path(request_path).parts:
        reconcile.fail("invalid registry-owned reconcile request path")
    canonical_url = f"https://github.com/{project['repository']}.git"
    reconcile.require(
        reconcile.run([
            "git", "-c", f"safe.directory={repo_root}", "-C", repo_root,
            "fetch", "--depth=64", canonical_url, source_ref,
        ]),
        "product request fetch",
    )
    shown = reconcile.require(
        reconcile.run([
            "git", "-c", f"safe.directory={repo_root}", "-C", repo_root,
            "show", f"FETCH_HEAD:{request_path}",
        ]),
        "product request read",
    )
    try:
        request = json.loads(shown.stdout)
    except json.JSONDecodeError:
        reconcile.fail("product reconcile request is not valid JSON")
    _, capability = reconcile.resolve_authority(request, registry)
    if request["project_id"] != reconcile.PROJECT_ID or request["capability"] != reconcile.CAPABILITY_ID:
        reconcile.fail("unexpected reconcile project/capability")
    return request, capability, ""


reconcile.as_user = direct_identity
reconcile.fetch_request = fetch_request_from_canonical_origin

if __name__ == "__main__":
    raise SystemExit(reconcile.main())
