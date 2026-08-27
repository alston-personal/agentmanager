"""Ubuntu-owned consumer for AgentOS Antigravity relay capsules.

Run this process as the human/IDE account (ubuntu), never as agentos-node. It
consumes bounded relay capsules, invokes a configured local executor without a
shell, and emits receipts for AgentOS reconciliation.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import glob
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any, Sequence

from .antigravity_relay import (
    EXECUTION_CONTEXT_SCHEMA,
    RELAY_SCHEMA,
    RECEIPT_SCHEMA,
    RelayPaths,
    share_relay_path,
    verify_capsule_digest,
)


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
    context = capsule.get("execution_context") if isinstance(capsule.get("execution_context"), dict) else {}
    goal = str(context.get("active_goal") or ir.get("goal") or "").strip()
    constraints = ir.get("constraints") if isinstance(ir.get("constraints"), list) else []
    findings = context.get("current_findings") if isinstance(context.get("current_findings"), list) else []
    next_actions = context.get("next_actions") if isinstance(context.get("next_actions"), list) else []
    next_action = str(context.get("next_action") or "").strip()
    freshness = context.get("context_freshness") if isinstance(context.get("context_freshness"), dict) else {}
    instruction = str(capsule.get("instruction") or "").strip()

    parts = [
        "You are a bounded weak executor inside AgentOS. The Kernel-supplied execution context is authoritative for continuity.",
        "Preserve the Master Experience Floor: reason from durable goals, findings, decisions and next actions rather than behaving like a stateless chat session.",
        "Do not invent missing state. Distinguish VERIFIED / RECONSTRUCTED / UNKNOWN. Do not claim side effects you did not perform.",
    ]
    if goal:
        parts.append(f"Active durable goal: {goal}")
    if findings:
        parts.append("Verified current findings: " + json.dumps(findings[:12], ensure_ascii=False))
    if next_action:
        parts.append(f"Kernel-recommended next action: {next_action}")
    if next_actions:
        parts.append("Durable next-action queue: " + json.dumps(next_actions[:8], ensure_ascii=False))
    if freshness:
        parts.append("Context freshness: " + json.dumps(freshness, ensure_ascii=False, sort_keys=True))
        if freshness.get("status") == "stale":
            parts.append("The durable context is marked stale. Reconcile evidence before taking irreversible action.")
    if constraints:
        parts.append("Canonical constraints: " + json.dumps(constraints, ensure_ascii=False))
    parts.append("Execution instruction: " + instruction)
    parts.append("Return the concrete result, evidence used, and next-action/blocked state. Keep continuity with the durable goal even if this is a fresh executor session.")
    return "\n\n".join(parts)


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
        for pattern_dir in (self.paths.inbox, self.paths.processing, self.paths.receipts):
            for artifact in pattern_dir.glob("relay-*.json*"):
                try:
                    share_relay_path(artifact)
                except OSError:
                    pass

    def process_one(self) -> dict[str, Any] | None:
        self._ensure_shared_spool()
        candidates = sorted(self.paths.inbox.glob("relay-*.json"))
        if not candidates:
            return None
        source = candidates[0]
        processing = self.paths.processing / source.name
        source.replace(processing)
        share_relay_path(processing)
        started = _utc_now()
        try:
            capsule = json.loads(processing.read_text(encoding="utf-8"))
            if not isinstance(capsule, dict) or capsule.get("schema") != RELAY_SCHEMA:
                raise ValueError("invalid relay capsule")
            if not verify_capsule_digest(capsule):
                raise ValueError("relay capsule digest mismatch")
            capsule_id = str(capsule.get("capsule_id") or "").strip()
            execution_context = capsule.get("execution_context")
            if not isinstance(execution_context, dict) or execution_context.get("schema") != EXECUTION_CONTEXT_SCHEMA:
                raise ValueError("relay capsule missing valid execution_context")
            if str(execution_context.get("project_id") or "") != str(capsule.get("project_id") or ""):
                raise ValueError("relay execution_context project mismatch")
            workspace = Path(str(capsule.get("workspace") or "")).expanduser()
            if not capsule_id:
                raise ValueError("capsule_id missing")
            if not workspace.is_dir():
                raise ValueError(f"workspace unavailable: {workspace}")
            if not self.executor:
                raise RuntimeError("no authorized local Antigravity executor discovered")

            completed = subprocess.run(
                [*self.executor, build_prompt(capsule)],
                cwd=str(workspace),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
            receipt: dict[str, Any] = {
                "schema": RECEIPT_SCHEMA,
                "capsule_id": capsule_id,
                "started_at": started,
                "completed_at": _utc_now(),
                "executor_user": os.environ.get("USER") or str(os.getuid()),
                "executor": self.executor[0],
                "returncode": completed.returncode,
                "ok": completed.returncode == 0,
                "context_source_revision": execution_context.get("source_revision"),
                "context_freshness": execution_context.get("context_freshness"),
                "stdout": completed.stdout[-100000:],
                "stderr": completed.stderr[-20000:],
            }
        except Exception as exc:
            capsule_id = locals().get("capsule_id") or processing.stem
            receipt = {
                "schema": RECEIPT_SCHEMA,
                "capsule_id": capsule_id,
                "started_at": started,
                "completed_at": _utc_now(),
                "executor_user": os.environ.get("USER") or str(os.getuid()),
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
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
            processed = self.process_one()
            if processed is None:
                time.sleep(interval)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ubuntu-owned AgentOS Antigravity relay worker")
    parser.add_argument("--root", default=str(Path.home() / "agent-data/runtime/antigravity-relay"))
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args(argv)

    worker = AntigravityRelayWorker(args.root)
    if args.once:
        result = worker.process_one()
        print(json.dumps(result or {"status": "idle"}, ensure_ascii=False, indent=2))
        return 0
    worker.serve(interval=args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
