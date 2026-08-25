"""Ubuntu-owned consumer for AgentOS Antigravity relay capsules.

The worker is intentionally conservative at the cross-user boundary: peer-owned
capsules may already have the correct shared group/mode even when chown/chmod is
not permitted to the consumer. Such artifacts are verified rather than rejected.
Stranded processing capsules are recovered after a restart when they are readable.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import glob
import json
import os
from pathlib import Path
import stat
import subprocess
import time
from typing import Any, Sequence

from .antigravity_relay import RELAY_SCHEMA, RECEIPT_SCHEMA, RelayPaths, share_relay_path


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def discover_executor() -> list[str] | None:
    explicit = os.environ.get("AGENTOS_ANTIGRAVITY_EXECUTOR")
    if explicit:
        candidate = Path(explicit).expanduser()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return [str(candidate), "--bare", "--print", "--output-format", "text", "--effort", "low"]
    patterns = [
        str(Path.home() / ".antigravity-ide-server/extensions/anthropic.claude-code-*-linux-arm64/resources/native-binary/claude"),
        str(Path.home() / ".antigravity-ide-server/extensions/anthropic.claude-code-*/resources/native-binary/claude"),
    ]
    matches: list[str] = []
    for pattern in patterns:
        matches.extend(glob.glob(pattern))
    for item in sorted(set(matches), reverse=True):
        candidate = Path(item)
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return [str(candidate), "--bare", "--print", "--output-format", "text", "--effort", "low"]
    return None


def build_prompt(capsule: dict[str, Any]) -> str:
    ir = capsule.get("canonical_ir") if isinstance(capsule.get("canonical_ir"), dict) else {}
    goal = str(ir.get("goal") or "").strip()
    constraints = ir.get("constraints") if isinstance(ir.get("constraints"), list) else []
    instruction = str(capsule.get("instruction") or "").strip()
    parts = [
        "You are an executor inside AgentOS. Treat the supplied Canonical IR as authoritative context.",
        "Do not invent missing state. Distinguish VERIFIED / RECONSTRUCTED / UNKNOWN.",
    ]
    if goal:
        parts.append(f"Canonical goal: {goal}")
    if constraints:
        parts.append("Constraints: " + json.dumps(constraints, ensure_ascii=False))
    parts.append("Execution instruction: " + instruction)
    parts.append("Return concrete result and blocked evidence. Do not claim side effects you did not perform.")
    return "\n\n".join(parts)


def _readable_shared_file(path: Path) -> bool:
    try:
        st = path.stat()
    except OSError:
        return False
    mode = stat.S_IMODE(st.st_mode)
    return path.is_file() and os.access(path, os.R_OK) and bool(mode & 0o040)


class AntigravityRelayWorker:
    def __init__(self, root: str | Path, *, executor: Sequence[str] | None = None, timeout: float = 180.0) -> None:
        self.paths = RelayPaths(Path(root).expanduser())
        self.executor = list(executor) if executor else discover_executor()
        self.timeout = timeout

    def _ensure_shared_spool(self) -> None:
        self.paths.ensure()
        for path in (self.paths.root, self.paths.inbox, self.paths.processing, self.paths.receipts):
            try:
                share_relay_path(path, directory=True)
            except PermissionError:
                pass

    def _next_capsule(self) -> tuple[Path, bool] | None:
        inbox = sorted(self.paths.inbox.glob("relay-*.json"))
        if inbox:
            return inbox[0], False
        # Recover capsules stranded after a worker crash. Skip artifacts which the
        # ubuntu boundary cannot actually read instead of crash-looping forever.
        for path in sorted(self.paths.processing.glob("relay-*.json")):
            if _readable_shared_file(path):
                return path, True
        return None

    def process_one(self) -> dict[str, Any] | None:
        self._ensure_shared_spool()
        chosen = self._next_capsule()
        if chosen is None:
            return None
        source, already_processing = chosen
        processing = source if already_processing else self.paths.processing / source.name
        if not already_processing:
            source.replace(processing)
        try:
            share_relay_path(processing)
        except PermissionError:
            # Moving a peer-owned file preserves its owner. If the artifact is
            # already group-readable/writable, the ownership operation is not a
            # validity requirement for consuming it.
            if not (os.access(processing, os.R_OK) and os.access(processing, os.W_OK)):
                raise
        started = _utc_now()
        capsule_id = processing.stem
        try:
            capsule = json.loads(processing.read_text(encoding="utf-8"))
            if not isinstance(capsule, dict) or capsule.get("schema") != RELAY_SCHEMA:
                raise ValueError("invalid relay capsule")
            capsule_id = str(capsule.get("capsule_id") or "").strip()
            workspace = Path(str(capsule.get("workspace") or "")).expanduser()
            if not capsule_id:
                raise ValueError("capsule_id missing")
            if not workspace.is_dir():
                raise ValueError(f"workspace unavailable: {workspace}")
            if not self.executor:
                raise RuntimeError("no authorized local Antigravity executor discovered")
            completed = subprocess.run(
                [*self.executor, build_prompt(capsule)], cwd=str(workspace), capture_output=True,
                text=True, timeout=self.timeout, check=False,
            )
            receipt: dict[str, Any] = {
                "schema": RECEIPT_SCHEMA, "capsule_id": capsule_id, "started_at": started,
                "completed_at": _utc_now(), "executor_user": os.environ.get("USER") or str(os.getuid()),
                "executor": self.executor[0], "returncode": completed.returncode,
                "ok": completed.returncode == 0, "stdout": completed.stdout[-100000:],
                "stderr": completed.stderr[-20000:],
            }
        except Exception as exc:
            receipt = {
                "schema": RECEIPT_SCHEMA, "capsule_id": capsule_id, "started_at": started,
                "completed_at": _utc_now(), "executor_user": os.environ.get("USER") or str(os.getuid()),
                "ok": False, "error": f"{type(exc).__name__}: {exc}",
            }
        target = self.paths.receipts / f"{receipt['capsule_id']}.json"
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        share_relay_path(tmp)
        tmp.replace(target)
        share_relay_path(target)
        processing.unlink(missing_ok=True)
        return receipt

    def serve(self, *, interval: float = 1.0) -> None:
        self._ensure_shared_spool()
        while True:
            if self.process_one() is None:
                time.sleep(interval)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ubuntu-owned AgentOS Antigravity relay worker")
    parser.add_argument("--root", default=str(Path.home() / "agent-data/runtime/antigravity-relay"))
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args(argv)
    worker = AntigravityRelayWorker(args.root)
    if args.once:
        print(json.dumps(worker.process_one() or {"status": "idle"}, ensure_ascii=False, indent=2))
        return 0
    worker.serve(interval=args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
