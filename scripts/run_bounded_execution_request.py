#!/usr/bin/env python3
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ALLOWED = {
    "leopardcat.production.parity.inspect": {
        "project_id": "leopardcat-tarot",
        "repository": "alston-personal/leopardcat-tarot",
        "environment": "production",
        "listen_port": 8088,
        "repo_root": "/home/ubuntu/leopardcat-tarot",
        "public_origin": "https://leopardcat-tarot.milkcat.org",
    }
}
SHA40 = re.compile(r"^[0-9a-f]{40}$")
ASSET_RE = re.compile(rb'src="(/assets/index-[^"]+\.js)"')


def now():
    return datetime.now(timezone.utc).isoformat()


def run_fixed(argv):
    return subprocess.run(argv, text=True, capture_output=True, check=False)


def fail(msg):
    raise RuntimeError(msg)


def load_request(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    required = {
        "schema", "request_id", "project_id", "repository", "source_ref",
        "source_sha", "capability", "environment", "parameters", "expected_result"
    }
    if set(data) != required:
        fail(f"request keys mismatch: {sorted(set(data) ^ required)}")
    if data["schema"] != "agentos.execution-request/v1":
        fail("unsupported request schema")
    if data["expected_result"] != "agentos.execution-receipt/v1":
        fail("unsupported receipt schema")
    if not SHA40.fullmatch(data["source_sha"]):
        fail("source_sha must be an exact lowercase 40-char SHA")
    policy = ALLOWED.get(data["capability"])
    if not policy:
        fail("capability not allowlisted")
    for key in ("project_id", "repository", "environment"):
        if data[key] != policy[key]:
            fail(f"{key} is outside capability authority")
    params = data["parameters"]
    if set(params) != {"listen_port"} or params["listen_port"] != policy["listen_port"]:
        fail("parameters outside typed capability contract")
    if data["source_ref"] != "main":
        fail("LeopardCat production parity currently authorizes source_ref=main only")
    return data, policy


def inspect_listener(port):
    proc = run_fixed(["ss", "-ltnp", f"sport = :{port}"])
    text = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0 or "LISTEN" not in text:
        fail(f"no listener on port {port}: {text.strip()[:500]}")
    m = re.search(r"pid=(\d+)", text)
    return {"present": True, "pid": int(m.group(1)) if m else None, "ss": text.strip()[:1000]}


def git_state(repo_root):
    def git(*args):
        p = run_fixed(["git", "-C", repo_root, *args])
        if p.returncode != 0:
            fail(f"git {' '.join(args)} failed: {(p.stderr or p.stdout).strip()[:500]}")
        return p.stdout.strip()
    head = git("rev-parse", "HEAD")
    branch = git("branch", "--show-current")
    remote = git("remote", "get-url", "origin")
    porcelain = git("status", "--porcelain")
    dirty_paths = []
    for line in porcelain.splitlines():
        path = line[3:] if len(line) > 3 else ""
        dirty_paths.append(path)
    def allowed_dirty(path):
        return (
            path == "website/dist/index.html"
            or path == "website/stats.json"
            or path.startswith("website/node_modules/.vite/")
        )
    unexpected = [p for p in dirty_paths if not allowed_dirty(p)]
    return {
        "root": repo_root,
        "head": head,
        "branch": branch,
        "remote_origin": remote,
        "dirty_paths": dirty_paths,
        "unexpected_dirty_paths": unexpected,
    }


def fetch_bytes(url):
    req = urllib.request.Request(url, headers={"User-Agent": "agentos-bounded-parity/1"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read(), getattr(r, "status", 200)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def main():
    if len(sys.argv) not in (2, 3):
        print("usage: run_bounded_execution_request.py REQUEST.json [RECEIPT.json]", file=sys.stderr)
        return 2
    out_path = Path(sys.argv[2] if len(sys.argv) == 3 else ".agentos/evidence/execution-receipt.json")
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
        "executor_identity": os.environ.get("RUNNER_NAME") or os.uname().nodename,
        "started_at": now(),
        "completed_at": None,
        "evidence": {},
        "error": None,
    }
    try:
        request, policy = load_request(sys.argv[1])
        for k in ("request_id", "project_id", "repository", "environment", "source_ref", "source_sha", "capability"):
            receipt[k] = request[k]

        port = policy["listen_port"]
        repo_root = policy["repo_root"]
        public_origin = policy["public_origin"]
        listener = inspect_listener(port)
        runtime_git = git_state(repo_root)

        dist_index_path = Path(repo_root) / "website" / "dist" / "index.html"
        if not dist_index_path.is_file():
            fail(f"missing production dist index: {dist_index_path}")
        dist_index = dist_index_path.read_bytes()
        m = ASSET_RE.search(dist_index)
        if not m:
            fail("unable to resolve hashed Vite JS asset from dist/index.html")
        asset_path = m.group(1).decode("utf-8")
        local_asset_path = Path(repo_root) / "website" / "dist" / asset_path.lstrip("/")
        if not local_asset_path.is_file():
            fail(f"missing local built asset: {local_asset_path}")
        local_asset = local_asset_path.read_bytes()
        localhost_asset, localhost_status = fetch_bytes(f"http://127.0.0.1:{port}{asset_path}")
        public_asset, public_status = fetch_bytes(f"{public_origin}{asset_path}")
        public_root, public_root_status = fetch_bytes(f"{public_origin}/")

        local_digest = sha256(local_asset)
        localhost_digest = sha256(localhost_asset)
        public_digest = sha256(public_asset)

        source_main = (Path(repo_root) / "website" / "main.js").read_bytes()
        source_v2_runtime = b"platform === 'MacIntel' && touchPoints > 1" in source_main
        source_v2_restore = b"restoredSpread === 'single' && restoredCards.length <= 1" in source_main
        bundle_v2_runtime = b"MacIntel" in public_asset and b"maxTouchPoints" in public_asset and b"standalone" in public_asset

        repo_matches = "leopardcat-tarot" in runtime_git["remote_origin"]
        exact_head = runtime_git["head"] == request["source_sha"]
        branch_ok = runtime_git["branch"] == "main"
        dirty_ok = not runtime_git["unexpected_dirty_paths"]
        artifact_three_way = local_digest == localhost_digest == public_digest
        http_ok = localhost_status == 200 and public_status == 200 and public_root_status == 200

        accepted = all([
            listener["present"], repo_matches, exact_head, branch_ok, dirty_ok,
            artifact_three_way, http_ok, source_v2_runtime, source_v2_restore, bundle_v2_runtime,
        ])
        receipt["result_status"] = "success" if accepted else "mismatch"
        receipt["evidence_level"] = "runtime_repo+deployed_artifact"
        receipt["artifact_digest"] = public_digest
        receipt["evidence"] = {
            "listener": listener,
            "runtime_git": runtime_git,
            "repository_matches": repo_matches,
            "requested_source_sha_matches_runtime_head": exact_head,
            "runtime_branch_is_main": branch_ok,
            "runtime_dirty_state_allowed": dirty_ok,
            "vite_asset_path": asset_path,
            "local_asset_sha256": local_digest,
            "localhost_asset_sha256": localhost_digest,
            "public_asset_sha256": public_digest,
            "artifact_three_way_match": artifact_three_way,
            "localhost_asset_http": localhost_status,
            "public_asset_http": public_status,
            "public_root_http": public_root_status,
            "source_v2_runtime_marker": source_v2_runtime,
            "source_v2_restore_marker": source_v2_restore,
            "public_bundle_v2_runtime_markers": bundle_v2_runtime,
            "public_origin": public_origin,
        }
    except Exception as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        receipt["completed_at"] = now()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["result_status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
