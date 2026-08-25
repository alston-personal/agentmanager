from __future__ import annotations

import argparse
import grp
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any, Callable
import uuid
from datetime import datetime, timezone

ACTION_SCHEMA = "agentos.action-relay/v1"
RECEIPT_SCHEMA = "agentos.action-receipt/v1"
SHARED_GROUP = "agentos"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def _share(path: Path, *, directory: bool = False) -> None:
    gid = grp.getgrnam(SHARED_GROUP).gr_gid
    try:
        os.chown(path, -1, gid)
    except PermissionError:
        pass
    try:
        os.chmod(path, 0o2770 if directory else 0o660)
    except PermissionError:
        if not directory:
            raise


class Paths:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.inbox = self.root / "inbox"
        self.processing = self.root / "processing"
        self.receipts = self.root / "receipts"

    def ensure(self) -> None:
        for p in (self.root, self.inbox, self.processing, self.receipts):
            p.mkdir(parents=True, exist_ok=True)
            _share(p, directory=True)


class ActionRelayClient:
    """Producer API. No command/shell text exists in the capsule contract."""

    def __init__(self, root: str | Path): self.paths = Paths(root)

    def submit(self, action: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        action = str(action or "").strip()
        if not action or not isinstance(params or {}, dict): raise ValueError("action and object params are required")
        if action not in ACTIONS: raise ValueError(f"unsupported action: {action}")
        self.paths.ensure(); capsule_id = f"action-{uuid.uuid4().hex}"
        payload: dict[str, Any] = {"schema": ACTION_SCHEMA,"capsule_id": capsule_id,"created_at": _now(),"action": action,"params": params or {},"authority": {"source": "agentos-node", "target_user": "ubuntu", "arbitrary_shell": False}}
        payload["digest"] = "sha256:" + hashlib.sha256(_canonical(payload)).hexdigest()
        tmp = self.paths.inbox / f"{capsule_id}.json.tmp"; target = self.paths.inbox / f"{capsule_id}.json"
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        _share(tmp); tmp.replace(target); _share(target)
        return payload

    def receipt(self, capsule_id: str) -> dict[str, Any] | None:
        p = self.paths.receipts / f"{capsule_id}.json"
        if not p.exists(): return None
        result = json.loads(p.read_text(encoding="utf-8"))
        if result.get("schema") != RECEIPT_SCHEMA: raise ValueError("invalid receipt")
        return result


def _run(argv: list[str], *, cwd: str | Path, timeout: int = 300) -> dict[str, Any]:
    completed = subprocess.run(argv, cwd=str(cwd), text=True, capture_output=True, timeout=timeout, check=False)
    return {"argv": argv, "returncode": completed.returncode, "stdout": completed.stdout[-30000:], "stderr": completed.stderr[-10000:]}


def _site_sync_build(params: dict[str, Any]) -> dict[str, Any]:
    site = params.get("site")
    if site != "studio.milkcat.org": raise ValueError("site is not allowlisted")
    repo = Path("/home/ubuntu/zeus-writer"); website = repo / "website"
    if not (repo / ".git").exists() or not (website / "package.json").exists(): raise RuntimeError("allowlisted site checkout unavailable")
    git = ["git", "-c", f"safe.directory={repo}", "-C", str(repo)]
    dirty = subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
    if dirty: raise RuntimeError("site checkout is dirty; refusing automated sync")
    steps = [_run(git + ["fetch", "origin", "master"], cwd=repo)]
    if steps[-1]["returncode"] != 0: return {"ok": False, "steps": steps}
    steps.append(_run(git + ["merge", "--ff-only", "origin/master"], cwd=repo))
    if steps[-1]["returncode"] != 0: return {"ok": False, "steps": steps}
    steps.append(_run(["npm", "run", "build"], cwd=website, timeout=600))
    ok = steps[-1]["returncode"] == 0 and (website / "dist" / "layout-lab" / "index.html").exists()
    return {"ok": ok, "site": site, "artifact": str(website / "dist" / "layout-lab" / "index.html"), "steps": steps}


def _layoutlab_api_restart(params: dict[str, Any]) -> dict[str, Any]:
    if params not in ({}, {"service": "layoutlab-api"}): raise ValueError("unexpected parameters")
    unit = "layoutlab-api.service"; step = _run(["systemctl", "--user", "restart", unit], cwd=Path.home(), timeout=30)
    return {"ok": step["returncode"] == 0, "service": unit, "step": step}


def _antigravity_restart(params: dict[str, Any]) -> dict[str, Any]:
    if params not in ({}, {"service": "agentos-antigravity-relay"}): raise ValueError("unexpected parameters")
    unit = "agentos-antigravity-relay.service"
    step = _run(["systemctl", "--user", "restart", unit], cwd=Path.home(), timeout=30)
    # The caller is a separate Action Relay service, so restarting Antigravity does
    # not terminate the action currently producing this receipt.
    return {"ok": step["returncode"] == 0, "service": unit, "step": step}


ACTIONS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "site.sync_build": _site_sync_build,
    "layoutlab.api.restart": _layoutlab_api_restart,
    "agentos.antigravity.restart": _antigravity_restart,
}


class ActionRelayWorker:
    """Ubuntu-owned deterministic consumer. It never invokes a shell or LLM."""
    def __init__(self, root: str | Path): self.paths = Paths(root)
    def process_one(self) -> dict[str, Any] | None:
        self.paths.ensure(); candidates = sorted(self.paths.inbox.glob("action-*.json"))
        if not candidates: return None
        source = candidates[0]; processing = self.paths.processing / source.name; source.replace(processing); _share(processing)
        started = _now(); capsule_id = processing.stem
        try:
            capsule = json.loads(processing.read_text(encoding="utf-8"))
            if capsule.get("schema") != ACTION_SCHEMA: raise ValueError("invalid action schema")
            capsule_id = str(capsule.get("capsule_id") or ""); action = str(capsule.get("action") or ""); params = capsule.get("params")
            if not capsule_id or action not in ACTIONS or not isinstance(params, dict): raise ValueError("invalid action capsule")
            supplied = str(capsule.get("digest") or ""); unsigned = dict(capsule); unsigned.pop("digest", None)
            expected = "sha256:" + hashlib.sha256(_canonical(unsigned)).hexdigest()
            if supplied != expected: raise ValueError("capsule digest mismatch")
            result = ACTIONS[action](params)
            receipt = {"schema": RECEIPT_SCHEMA,"capsule_id": capsule_id,"action": action,"started_at": started,"completed_at": _now(),"executor_user": os.environ.get("USER") or str(os.getuid()),**result}
        except Exception as exc:
            receipt = {"schema": RECEIPT_SCHEMA,"capsule_id": capsule_id,"started_at": started,"completed_at": _now(),"executor_user": os.environ.get("USER") or str(os.getuid()),"ok": False,"error": f"{type(exc).__name__}: {exc}"}
        target = self.paths.receipts / f"{capsule_id}.json"; tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(receipt, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        _share(tmp); tmp.replace(target); _share(target); processing.unlink(missing_ok=True); return receipt
    def serve(self, interval: float = 1.0) -> None:
        while True:
            if self.process_one() is None: time.sleep(interval)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(); p.add_argument("--root", required=True); p.add_argument("--once", action="store_true")
    args = p.parse_args(argv); worker = ActionRelayWorker(args.root)
    if args.once: print(json.dumps(worker.process_one() or {"status":"idle"}, indent=2, ensure_ascii=False)); return 0
    worker.serve(); return 0

if __name__ == "__main__": raise SystemExit(main())
