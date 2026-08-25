"""Cross-user relay boundary for an ubuntu-owned Antigravity executor."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import grp, hashlib, json, os, uuid
from pathlib import Path
from typing import Any

RELAY_SCHEMA = "agentos.antigravity-relay/v1"
RECEIPT_SCHEMA = "agentos.antigravity-receipt/v1"
SHARED_GROUP = "agentos"
SHARED_DIR_MODE = 0o2770
SHARED_FILE_MODE = 0o660

def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

def _shared_gid() -> int:
    return grp.getgrnam(SHARED_GROUP).gr_gid

def share_relay_path(path: Path, *, directory: bool = False) -> None:
    try:
        os.chown(path, -1, _shared_gid())
    except PermissionError:
        pass
    try:
        os.chmod(path, SHARED_DIR_MODE if directory else SHARED_FILE_MODE)
    except PermissionError:
        if not directory:
            raise

@dataclass(frozen=True)
class RelayPaths:
    root: Path
    @property
    def inbox(self) -> Path: return self.root / "inbox"
    @property
    def processing(self) -> Path: return self.root / "processing"
    @property
    def receipts(self) -> Path: return self.root / "receipts"
    def ensure(self) -> None:
        for path in (self.root, self.inbox, self.processing, self.receipts):
            path.mkdir(parents=True, exist_ok=True)
            share_relay_path(path, directory=True)

class AntigravityRelayClient:
    def __init__(self, root: str | Path) -> None:
        self.paths = RelayPaths(Path(root).expanduser())
    def submit(self, *, project_id: str, canonical_ir: dict[str, Any], instruction: str, workspace: str, executor_hint: str = "antigravity") -> dict[str, Any]:
        if not project_id or not instruction or not workspace or not isinstance(canonical_ir, dict):
            raise ValueError("project_id, canonical_ir, instruction, and workspace are required")
        self.paths.ensure()
        capsule_id = f"relay-{uuid.uuid4().hex}"
        payload: dict[str, Any] = {
            "schema": RELAY_SCHEMA, "capsule_id": capsule_id, "created_at": _utc_now(),
            "project_id": project_id, "workspace": workspace, "executor_hint": executor_hint,
            "instruction": instruction, "canonical_ir": canonical_ir,
            "authority": {"source": "agentos-node", "desktop_user": "ubuntu", "direct_session_impersonation": False},
        }
        payload["digest"] = "sha256:" + hashlib.sha256(_canonical_bytes(payload)).hexdigest()
        target = self.paths.inbox / f"{capsule_id}.json"; tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        share_relay_path(tmp); tmp.replace(target); share_relay_path(target)
        return payload
    def receipt(self, capsule_id: str) -> dict[str, Any] | None:
        path = self.paths.receipts / f"{capsule_id}.json"
        if not path.exists(): return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema") != RECEIPT_SCHEMA: raise ValueError("invalid Antigravity relay receipt")
        return payload
