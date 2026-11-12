#!/usr/bin/env python3
"""Bounded read-only Oracle 8780 Realm Fabric loaded-source attestation.

No secret, raw unit, process argv, full environment, token, user path, or HTML
is ever emitted. File equality is a candidate on-disk observation, not an
in-memory module proof.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.request

SCHEMA = "agentos.realm-loaded-source-attestation/v1"
UNIT = "agentos-realm-fabric.service"
MODULE = "agent_core/realm_server.py"
ROOT = Path(__file__).resolve().parents[1]
EXPECTED = ROOT / MODULE


def sha256(path: Path) -> str | None:
    try:
        if not path.is_file() or path.stat().st_size > 2_000_000:
            return None
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except (OSError, ValueError):
        return None


def parse_environ(raw: bytes) -> list[Path]:
    # Extract only PYTHONPATH candidates. Never expose any environment value.
    paths: list[Path] = []
    for item in raw.split(b"\0"):
        if item.startswith(b"PYTHONPATH="):
            try:
                for segment in os.fsdecode(item.split(b"=", 1)[1]).split(os.pathsep):
                    if segment.startswith("/") and len(segment) < 256:
                        paths.append(Path(segment) / MODULE)
            except (UnicodeError, ValueError):
                continue
    return paths


def active_unit_state() -> tuple[str, int | None]:
    try:
        result = subprocess.run(
            ["/usr/bin/systemctl", "--user", "show", UNIT, "-p", "MainPID",
             "-p", "ActiveState", "--no-pager"],
            capture_output=True, text=True, timeout=6, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable", None
    if result.returncode != 0:
        return "unavailable", None
    values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    status = values.get("ActiveState", "unknown")
    raw_pid = values.get("MainPID", "")
    pid = int(raw_pid) if raw_pid.isdigit() and 1 <= int(raw_pid) < 10_000_000 else None
    return status if status in ("active", "inactive", "failed") else "unknown", pid


def probe_health() -> bool:
    try:
        with urllib.request.urlopen(
            urllib.request.Request("http://127.0.0.1:8780/v1/health",
                                   headers={"Accept": "application/json"}),
            timeout=4,
        ) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read(4096))
            return (
                isinstance(payload, dict)
                and payload.get("schema") == "agentos.one-health/v0.1"
                and payload.get("ok") is True
            )
    except (OSError, ValueError, urllib.error.URLError):
        return False


def source_attestation() -> dict:
    state, pid = active_unit_state()
    expected = sha256(EXPECTED)
    module_candidates: list[Path] = []
    if pid is not None:
        try:
            # Only a single well-known user service process; no process scanning.
            module_candidates = parse_environ(Path(f"/proc/{pid}/environ").read_bytes())
        except OSError:
            pass
        try:
            cwd = Path(os.readlink(f"/proc/{pid}/cwd"))
            module_candidates.append(cwd / MODULE)
        except OSError:
            pass
    # Canonical checkout is a candidate only, not proof of the running process.
    module_candidates.append(Path("/home/ubuntu/agentmanager") / MODULE)
    candidate_hashes = [sha256(p) for p in dict.fromkeys(module_candidates)]
    candidate_hashes = [h for h in candidate_hashes if h is not None]
    selected = candidate_hashes[0] if candidate_hashes else None

    # Imported interpreter state cannot be conclusively recovered from a file
    # on disk. Report source identity as advisory only, never promotion PASS.
    unit_file = Path("/home/ubuntu/.config/systemd/user/agentos-realm-fabric.service")
    try:
        raw_unit = unit_file.read_text(encoding="utf-8")
        unit_contains_approved_path = (
            "/home/ubuntu/agentmanager" in raw_unit
            or "/home/ubuntu/agent-data/releases/" in raw_unit
        )
    except (OSError, UnicodeError):
        unit_contains_approved_path = False

    return {
        "schema": SCHEMA,
        "read_only": True,
        "unit_active": state == "active",
        "unit_status": state,
        "unit_pid_present": pid is not None,
        "approved_unit_source_hint": unit_contains_approved_path,
        "expected_source_available": expected is not None,
        "process_candidate_source_available": bool(candidate_hashes),
        "process_candidate_matches_checkout": selected == expected if selected and expected else False,
        "multiple_candidate_generations": len(set(candidate_hashes)) > 1,
        "health_schema_valid": probe_health(),
        "loaded_module_in_memory_verified": False,
        "conclusive_8780_origin_verified": False,
        "release_accepted": False,
        "credential_exposed": False,
    }


if __name__ == "__main__":
    report = source_attestation()
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    if not report["unit_active"] or not report["health_schema_valid"]:
        raise SystemExit(2)
