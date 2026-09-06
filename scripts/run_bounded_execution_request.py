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
        "served_script_path": "/main.js",
    }
}
SHA40 = re.compile(r"^[0-9a-f]{40}$")


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
    if set(params) != {"listen_port", "served_script_path"}:
        fail("parameters outside typed capability contract")
    if params["listen_port"] != policy["listen_port"] or params["served_script_path"] != policy["served_script_path"]:
        fail("parameters outside allowlist")
    if data["source_ref"] != "main":
        fail("LeopardCat production parity currently authorizes source_ref=main only")
    return data


def inspect_listener(port):
    proc = run_fixed(["ss", "-ltnp", f"sport = :{port}"])
    text = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0 or "LISTEN" not in text:
        fail(f"no listener on port {port}: {text.strip()[:500]}")
    m = re.search(r"pid=(\d+)", text)
    if not m:
        return {"present": True, "pid": None, "cwd": None, "cmdline": None, "ss": text.strip()[:1000]}
    pid = int(m.group(1))
    try:
        cwd = os.readlink(f"/proc/{pid}/cwd")
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace").strip()
    except OSError:
        cwd, cmdline = None, None
    return {"present": True, "pid": pid, "cwd": cwd, "cmdline": cmdline, "ss": text.strip()[:1000]}


def inspect_git(cwd):
    if not cwd:
        return None
    def git(*args):
        p = run_fixed(["git", "-C", cwd, *args])
        if p.returncode != 0:
            return None
        return p.stdout.strip()
    head = git("rev-parse", "HEAD")
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    root = git("rev-parse", "--show-toplevel")
    remote = git("config", "--get", "remote.origin.url")
    status = git("status", "--porcelain")
    if not all(v is not None for v in (head, branch, root, remote, status)):
        return None
    return {"head": head, "branch": branch, "root": root, "remote_origin": remote, "dirty": bool(status)}


def fetch_bytes(url):
    req = urllib.request.Request(url, headers={"User-Agent": "agentos-bounded-parity/1"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def main():
    if len(sys.argv) not in (2, 3):
        print("usage: run_bounded_execution_request.py REQUEST.json [RECEIPT.json]", file=sys.stderr)
        return 2
    request_path = sys.argv[1]
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
        request = load_request(request_path)
        for k in ("request_id", "project_id", "repository", "environment", "source_ref", "source_sha", "capability"):
            receipt[k] = request[k]

        port = request["parameters"]["listen_port"]
        listener = inspect_listener(port)
        git_state = inspect_git(listener["cwd"])

        served_url = f"http://127.0.0.1:{port}{request['parameters']['served_script_path']}"
        served = fetch_bytes(served_url)
        source_url = f"https://raw.githubusercontent.com/{request['repository']}/{request['source_sha']}/website/main.js"
        source = fetch_bytes(source_url)
        served_digest = sha256(served)
        source_digest = sha256(source)
        exact_artifact = served_digest == source_digest
        marker_runtime = b"platform === 'MacIntel' && touchPoints > 1" in served
        marker_restore = b"restoredSpread === 'single' && restoredCards.length <= 1" in served

        repo_matches = None
        exact_head = None
        clean = None
        if git_state:
            expected_repo_tokens = ("alston-personal/leopardcat-tarot", "leopardcat-tarot.git")
            repo_matches = any(t in git_state["remote_origin"] for t in expected_repo_tokens)
            exact_head = git_state["head"] == request["source_sha"]
            clean = not git_state["dirty"]

        artifact_accepted = exact_artifact and marker_runtime and marker_restore
        process_accepted = git_state is not None and repo_matches and exact_head and clean
        receipt["result_status"] = "success" if artifact_accepted else "mismatch"
        receipt["evidence_level"] = "runtime_process+deployed_artifact" if process_accepted and artifact_accepted else "deployed_artifact"
        receipt["artifact_digest"] = served_digest
        receipt["evidence"] = {
            "listen_port": port,
            "listener": listener,
            "runtime_git": git_state,
            "repository_matches": repo_matches,
            "requested_source_sha_matches_runtime_head": exact_head,
            "runtime_git_clean": clean,
            "served_url": served_url,
            "served_main_js_sha256": served_digest,
            "requested_source_url": source_url,
            "requested_source_main_js_sha256": source_digest,
            "served_artifact_matches_requested_source": exact_artifact,
            "served_v2_runtime_marker": marker_runtime,
            "served_v2_restore_marker": marker_restore,
            "process_identity_observable": git_state is not None,
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
