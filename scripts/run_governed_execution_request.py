#!/usr/bin/env python3
"""AgentOS governed execution-request v1 dispatcher.

The request is data, never a shell command. Authority comes from the Core registry;
the product manifest may only select an allowlisted capability and its exact typed
parameters. Provider/deploy secrets are never accepted from or returned to a request.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SHA40 = re.compile(r"^[0-9a-f]{40}$")
ASSET_RE = re.compile(rb'src="(/assets/index-[^"]+\.js)"')
REQUEST_KEYS = {
    "schema", "request_id", "project_id", "repository", "source_ref",
    "source_sha", "capability", "environment", "parameters",
    "replay_policy", "expected_result",
}


def now():
    return datetime.now(timezone.utc).isoformat()


def run_fixed(argv):
    return subprocess.run(argv, text=True, capture_output=True, check=False)


def fail(message):
    raise RuntimeError(message)


def sanitize_remote(remote):
    remote = str(remote or "")
    if "://" in remote:
        remote = re.sub(r"(https?://)[^/@]+@", r"\1", remote)
    return remote


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def resolve_authority(request, registry):
    if set(request) != REQUEST_KEYS:
        fail(f"request keys mismatch: {sorted(set(request) ^ REQUEST_KEYS)}")
    if request["schema"] != "agentos.execution-request/v1":
        fail("unsupported request schema")
    if request["expected_result"] != "agentos.execution-receipt/v1":
        fail("unsupported receipt schema")
    if not SHA40.fullmatch(str(request["source_sha"])):
        fail("source_sha must be an exact lowercase 40-char SHA")
    if registry.get("schema") != "agentos.execution-authority/v1":
        fail("unsupported execution authority schema")

    project = registry.get("projects", {}).get(request["project_id"])
    capability = registry.get("capabilities", {}).get(request["capability"])
    if not project or not capability:
        fail("project or capability not allowlisted")
    if capability.get("project_id") != request["project_id"]:
        fail("capability is not authorized for project")
    if project.get("repository") != request["repository"]:
        fail("repository is outside Project Identity authority")
    if request["source_ref"] not in project.get("allowed_source_refs", []):
        fail("source_ref is outside release-lane authority")
    if capability.get("environment") != request["environment"]:
        fail("environment is outside capability authority")
    if capability.get("parameters") != request["parameters"]:
        fail("parameters are outside typed capability contract")
    if capability.get("replay_policy") != request["replay_policy"]:
        fail("replay policy mismatch")
    return project, capability


def _path_allowed(path, exact, prefixes):
    return path in exact or any(path.startswith(prefix) for prefix in prefixes)


def git_state(repo_root, allowed_dirty_exact=(), allowed_dirty_prefixes=()):
    def git(*args):
        proc = run_fixed(["git", "-C", repo_root, *args])
        if proc.returncode:
            fail(f"git {' '.join(args)} failed: {(proc.stderr or proc.stdout).strip()[:400]}")
        return proc.stdout.strip()

    paths = []
    for line in git("status", "--porcelain").splitlines():
        paths.append((line[2:] if len(line) > 2 else "").strip())

    exact = tuple(allowed_dirty_exact or ())
    prefixes = tuple(allowed_dirty_prefixes or ())
    return {
        "root": repo_root,
        "head": git("rev-parse", "HEAD"),
        "branch": git("branch", "--show-current"),
        "remote_origin": sanitize_remote(git("remote", "get-url", "origin")),
        "dirty_paths": paths,
        "unexpected_dirty_paths": [p for p in paths if not _path_allowed(p, exact, prefixes)],
    }


def listener_state(port):
    listener_proc = run_fixed(["ss", "-ltnp", f"sport = :{port}"])
    listener_text = (listener_proc.stdout or "") + (listener_proc.stderr or "")
    if listener_proc.returncode or "LISTEN" not in listener_text:
        fail(f"no listener on port {port}")
    pid_match = re.search(r"pid=(\d+)", listener_text)
    return {"present": True, "pid": int(pid_match.group(1)) if pid_match else None}


def branch_matches_policy(branch, source_ref, policy):
    if policy == "source_ref":
        return branch == source_ref
    if policy == "detached_or_source_ref":
        return branch in ("", source_ref)
    fail(f"unsupported runtime branch policy: {policy}")


def fetch_bytes(url):
    req = urllib.request.Request(url, headers={"User-Agent": "agentos-governed-execution/1"})
    with urllib.request.urlopen(req, timeout=15) as response:
        return response.read(), int(getattr(response, "status", 200))


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def inspect_leopardcat_parity(request, capability):
    runtime = capability["runtime"]
    repo_root = runtime["repo_root"]
    port = request["parameters"]["listen_port"]
    public_origin = runtime["public_origin"]

    listener = listener_state(port)
    state = git_state(
        repo_root,
        allowed_dirty_exact=("website/dist/index.html", "website/stats.json", ".claude/"),
        allowed_dirty_prefixes=("website/node_modules/.vite/", ".claude/"),
    )
    index_path = Path(repo_root) / "website" / "dist" / "index.html"
    if not index_path.is_file():
        fail("production dist/index.html is missing")
    match = ASSET_RE.search(index_path.read_bytes())
    if not match:
        fail("unable to resolve hashed Vite asset")
    asset_path = match.group(1).decode("utf-8")
    local_path = Path(repo_root) / "website" / "dist" / asset_path.lstrip("/")
    if not local_path.is_file():
        fail("local built asset is missing")

    local = local_path.read_bytes()
    localhost, localhost_http = fetch_bytes(f"http://127.0.0.1:{port}{asset_path}")
    public, public_http = fetch_bytes(f"{public_origin}{asset_path}")
    _, root_http = fetch_bytes(f"{public_origin}/")
    digests = [sha256(local), sha256(localhost), sha256(public)]

    expected_remote = f"https://github.com/{request['repository']}.git"
    evidence = {
        "listener": listener,
        "runtime_git": state,
        "repository_matches": state["remote_origin"] == expected_remote,
        "requested_source_sha_matches_runtime_head": state["head"] == request["source_sha"],
        "runtime_branch_matches_source_ref": state["branch"] == request["source_ref"],
        "runtime_dirty_state_allowed": not state["unexpected_dirty_paths"],
        "vite_asset_path": asset_path,
        "local_asset_sha256": digests[0],
        "localhost_asset_sha256": digests[1],
        "public_asset_sha256": digests[2],
        "artifact_three_way_match": len(set(digests)) == 1,
        "localhost_asset_http": localhost_http,
        "public_asset_http": public_http,
        "public_root_http": root_http,
        "public_origin": public_origin,
    }
    accepted = all([
        evidence["repository_matches"],
        evidence["requested_source_sha_matches_runtime_head"],
        evidence["runtime_branch_matches_source_ref"],
        evidence["runtime_dirty_state_allowed"],
        evidence["artifact_three_way_match"],
        localhost_http == 200,
        public_http == 200,
        root_http == 200,
    ])
    return evidence, digests[2], accepted, "runtime_repo+deployed_artifact"


def inspect_repository_service(request, capability):
    runtime = capability["runtime"]
    repo_root = runtime["repo_root"]
    port = request["parameters"]["listen_port"]
    health_path = runtime.get("health_path", "/healthz")
    if not isinstance(health_path, str) or not health_path.startswith("/") or "://" in health_path:
        fail("invalid registry-owned health path")

    listener = listener_state(port)
    state = git_state(
        repo_root,
        allowed_dirty_exact=runtime.get("allowed_dirty_exact", ()),
        allowed_dirty_prefixes=runtime.get("allowed_dirty_prefixes", ()),
    )
    health_body, health_http = fetch_bytes(f"http://127.0.0.1:{port}{health_path}")
    health_digest = sha256(health_body)
    try:
        health_payload = json.loads(health_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        health_payload = None

    expected_health = runtime.get("expected_health", {})
    health_matches_expected = isinstance(health_payload, dict) and all(
        health_payload.get(key) == value for key, value in expected_health.items()
    )
    expected_remote = f"https://github.com/{request['repository']}.git"
    branch_policy = runtime.get("branch_policy", "source_ref")
    runtime_branch_matches = branch_matches_policy(state["branch"], request["source_ref"], branch_policy)

    evidence = {
        "listener": listener,
        "runtime_git": state,
        "repository_matches": state["remote_origin"] == expected_remote,
        "requested_source_sha_matches_runtime_head": state["head"] == request["source_sha"],
        "runtime_branch_policy": branch_policy,
        "runtime_branch_matches_policy": runtime_branch_matches,
        "runtime_dirty_state_allowed": not state["unexpected_dirty_paths"],
        "health_path": health_path,
        "health_http": health_http,
        "health_response_sha256": health_digest,
        "health_matches_expected": health_matches_expected,
    }
    accepted = all([
        evidence["repository_matches"],
        evidence["requested_source_sha_matches_runtime_head"],
        evidence["runtime_branch_matches_policy"],
        evidence["runtime_dirty_state_allowed"],
        health_http == 200,
        evidence["health_matches_expected"],
    ])
    return evidence, None, accepted, "runtime_repo+service_endpoint"


ADAPTERS = {
    "leopardcat_production_parity_inspect": inspect_leopardcat_parity,
    "repository_service_inspect": inspect_repository_service,
}


def main():
    if len(sys.argv) not in (2, 3, 4):
        print("usage: run_governed_execution_request.py REQUEST [RECEIPT] [REGISTRY]", file=sys.stderr)
        return 2
    request_path = sys.argv[1]
    receipt_path = Path(sys.argv[2] if len(sys.argv) >= 3 else ".agentos/evidence/execution-receipt.json")
    registry_path = sys.argv[3] if len(sys.argv) >= 4 else "governance/execution-authority.json"
    receipt = {
        "schema": "agentos.execution-receipt/v1",
        "request_id": None,
        "project_id": None,
        "repository": None,
        "environment": None,
        "source_ref": None,
        "source_sha": None,
        "capability": None,
        "result_status": "failed",
        "evidence_level": None,
        "artifact_digest": None,
        "executor_identity": os.environ.get("RUNNER_NAME") or os.uname().nodename,
        "started_at": now(),
        "completed_at": None,
        "evidence": {},
        "error": None,
    }
    try:
        request = load_json(request_path)
        _, capability = resolve_authority(request, load_json(registry_path))
        for key in ("request_id", "project_id", "repository", "environment", "source_ref", "source_sha", "capability"):
            receipt[key] = request[key]
        adapter = ADAPTERS.get(capability.get("adapter"))
        if not adapter:
            fail("capability adapter is not installed")
        evidence, digest, accepted, evidence_level = adapter(request, capability)
        receipt["evidence"] = evidence
        receipt["artifact_digest"] = digest
        receipt["evidence_level"] = evidence_level
        receipt["result_status"] = "success" if accepted else "mismatch"
    except Exception as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        receipt["completed_at"] = now()
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["result_status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
