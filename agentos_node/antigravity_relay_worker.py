"""Ubuntu-owned consumer for AgentOS Antigravity relay capsules.

The relay is an execution boundary, not an at-least-once queue. A capsule that
has already entered ``processing`` may have produced side effects before a
worker crash, so replaying it automatically is unsafe. New workers consume only
``inbox`` capsules. Stranded ``processing`` artifacts are forensic evidence and
must be reconciled/quarantined explicitly before any intentional replay.

Transport and model execution are intentionally separate concerns. The relay
accepts a small, fixed provider set instead of treating an IDE-private binary as
the identity of the Antigravity surface itself.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import glob
import json
import os
from pathlib import Path
import signal
import subprocess
import time
from typing import Any, Sequence

from .antigravity_relay import RELAY_SCHEMA, RECEIPT_SCHEMA, RelayPaths, share_relay_path


SUPPORTED_PROVIDERS = {"claude", "agy", "gemini"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _discover_claude() -> list[str] | None:
    # Preserve the ubuntu-owned Claude/Antigravity login identity. Claude
    # `--bare` intentionally bypasses OAuth/keychain subscription auth,
    # which is incompatible with this relay boundary. `--print` remains
    # the fixed non-interactive execution mode; capsules still cannot
    # provide argv, credentials, provider selection, or timeout values.
    explicit = os.environ.get("AGENTOS_ANTIGRAVITY_EXECUTOR")
    if explicit:
        candidate = Path(explicit).expanduser()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return [str(candidate), "--print", "--output-format", "text", "--effort", "low"]
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
            return [str(candidate), "--print", "--output-format", "text", "--effort", "low"]
    return None


def _discover_agy() -> list[str] | None:
    # Deliberately fixed to the ubuntu-owned AgentOS CLI location. Do not turn
    # this into arbitrary command text from a capsule or environment variable.
    candidate = Path.home() / ".local/bin/agy"
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return [str(candidate)]
    return None


def _discover_gemini() -> list[str] | None:
    candidate = Path.home() / ".local/bin/gemini"
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return [str(candidate)]
    return None


def discover_executor(provider: str | None = None) -> tuple[str, list[str] | None]:
    selected = str(provider or os.environ.get("AGENTOS_ANTIGRAVITY_PROVIDER") or "claude").strip().lower()
    if selected not in SUPPORTED_PROVIDERS:
        raise ValueError(f"unsupported Antigravity executor provider: {selected}")
    if selected == "agy":
        return selected, _discover_agy()
    if selected == "gemini":
        return selected, _discover_gemini()
    return selected, _discover_claude()


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


class AntigravityRelayWorker:
    def __init__(
        self,
        root: str | Path,
        *,
        executor: Sequence[str] | None = None,
        provider: str | None = None,
        timeout: float = 180.0,
    ) -> None:
        self.paths = RelayPaths(Path(root).expanduser())
        if executor is not None:
            # Test/in-process injection only. Production discovery remains a
            # fixed provider contract.
            self.provider = str(provider or "injected")
            self.executor = list(executor)
        else:
            self.provider, discovered = discover_executor(provider)
            self.executor = discovered
        self.timeout = timeout

    def _ensure_shared_spool(self) -> None:
        self.paths.ensure()
        for path in (self.paths.root, self.paths.inbox, self.paths.processing, self.paths.receipts):
            try:
                share_relay_path(path, directory=True)
            except PermissionError:
                pass

    def _next_capsule(self) -> Path | None:
        inbox = sorted(self.paths.inbox.glob("relay-*.json"))
        return inbox[0] if inbox else None

    def reconcile_stranded_processing(self, *, stale_after: float | None = None) -> int:
        self._ensure_shared_spool()
        threshold = max(600.0, float(stale_after if stale_after is not None else self.timeout * 3.0))
        quarantine = self.paths.root / "quarantine"
        quarantine.mkdir(parents=True, exist_ok=True)
        share_relay_path(quarantine, directory=True)
        now = time.time()
        reconciled = 0
        for source in sorted(self.paths.processing.glob("relay-*.json")):
            try:
                age = max(0.0, now - source.stat().st_mtime)
            except FileNotFoundError:
                continue
            if age < threshold:
                continue
            capsule_id = source.stem
            created_at = None
            try:
                payload = json.loads(source.read_text(encoding="utf-8"))
                capsule_id = str(payload.get("capsule_id") or capsule_id).strip() or capsule_id
                created_at = payload.get("created_at")
            except Exception:
                payload = {}
            receipt = {
                "schema": RECEIPT_SCHEMA,
                "capsule_id": capsule_id,
                "started_at": str(created_at or _utc_now()),
                "completed_at": _utc_now(),
                "executor_user": os.environ.get("USER") or str(os.getuid()),
                "provider": self.provider,
                "ok": False,
                "error": "StrandedProcessingCapsule: prior execution state UNKNOWN; automatic replay disabled",
                "classification": "UNKNOWN_SIDE_EFFECT",
                "timed_out": False,
            }
            target = self.paths.receipts / f"{capsule_id}.json"
            if not target.exists():
                tmp = target.with_suffix(target.suffix + ".tmp")
                tmp.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                share_relay_path(tmp)
                tmp.replace(target)
                share_relay_path(target)
            quarantined = quarantine / source.name
            source.replace(quarantined)
            share_relay_path(quarantined)
            reconciled += 1
        return reconciled

    def _executor_argv(self, capsule: dict[str, Any], workspace: Path) -> list[str]:
        if not self.executor:
            raise RuntimeError(f"no authorized local Antigravity executor discovered for provider={self.provider}")
        prompt = build_prompt(capsule)
        if self.provider == "agy":
            return [*self.executor, "run", "--task", prompt, "--workspace", str(workspace)]
        if self.provider == "gemini":
            return [*self.executor, "--skip-trust", "--approval-mode", "auto_edit", "--output-format", "text", "-p", prompt]
        return [*self.executor, prompt]

    def _run_executor(self, capsule: dict[str, Any], workspace: Path) -> dict[str, Any]:
        provider = self.provider
        executor = self.executor
        hint = str(capsule.get("executor_hint") or "").strip().lower()
        if hint in {"provider:claude", "provider:agy", "provider:gemini"}:
            provider, executor = discover_executor(hint.split(":", 1)[1])
        if not executor:
            raise RuntimeError(f"no authorized local Antigravity executor discovered for provider={provider}")
        prompt = build_prompt(capsule)
        if provider == "agy":
            argv = [*executor, "run", "--task", prompt, "--workspace", str(workspace)]
        else:
            argv = [*executor, prompt]
        proc = subprocess.Popen(
            argv,
            cwd=str(workspace),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        timed_out = False
        try:
            stdout, stderr = proc.communicate(timeout=self.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                stdout, stderr = proc.communicate(timeout=3.0)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                stdout, stderr = proc.communicate()
        if timed_out:
            stderr = (stderr or "") + f"\nAgentOS executor timeout after {self.timeout:.1f}s; process group terminated.\n"
        return {
            "provider": provider,
            "executor": executor[0] if executor else None,
            "returncode": 124 if timed_out else int(proc.returncode or 0),
            "stdout": (stdout or "")[-100000:],
            "stderr": (stderr or "")[-20000:],
            "timed_out": timed_out,
        }

    def process_one(self) -> dict[str, Any] | None:
        self._ensure_shared_spool()
        source = self._next_capsule()
        if source is None:
            return None
        processing = self.paths.processing / source.name
        source.replace(processing)
        try:
            share_relay_path(processing)
        except PermissionError:
            # Moving a peer-owned file preserves its owner. If the artifact is
            # already readable/writable by this explicitly authorized boundary,
            # ownership rewriting is not required for consumption.
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
            result = self._run_executor(capsule, workspace)
            receipt: dict[str, Any] = {
                "schema": RECEIPT_SCHEMA,
                "capsule_id": capsule_id,
                "started_at": started,
                "completed_at": _utc_now(),
                "executor_user": os.environ.get("USER") or str(os.getuid()),
                "provider": result.get("provider") or self.provider,
                "executor": result.get("executor") or (self.executor[0] if self.executor else None),
                "returncode": result["returncode"],
                "ok": result["returncode"] == 0 and not result["timed_out"],
                "timed_out": result["timed_out"],
                "stdout": result["stdout"],
                "stderr": result["stderr"],
            }
        except Exception as exc:
            receipt = {
                "schema": RECEIPT_SCHEMA,
                "capsule_id": capsule_id,
                "started_at": started,
                "completed_at": _utc_now(),
                "executor_user": os.environ.get("USER") or str(os.getuid()),
                "provider": self.provider,
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
        self.reconcile_stranded_processing()
        while True:
            if self.process_one() is None:
                time.sleep(interval)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ubuntu-owned AgentOS Antigravity relay worker")
    parser.add_argument("--root", default=str(Path.home() / "agent-data/runtime/antigravity-relay"))
    parser.add_argument("--provider", choices=sorted(SUPPORTED_PROVIDERS), default=None)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args(argv)
    worker = AntigravityRelayWorker(args.root, provider=args.provider)
    if args.once:
        worker.reconcile_stranded_processing()
        print(json.dumps(worker.process_one() or {"status": "idle", "provider": worker.provider}, ensure_ascii=False, indent=2))
        return 0
    worker.serve(interval=args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
