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


def is_realm_8780_command(raw: bytes) -> bool:
    """Only identify the already-known Realm listener; never emit cmdline."""
    parts = [part for part in raw.split(b"\0") if part]
    return (
        (b"agent_core.realm_cli" in parts or
         any(part.endswith(b"/agentos-one") for part in parts))
        and b"8780" in parts
        and b"serve" in parts
    )


def public_proc_candidates() -> list[int]:
    """Bounded /proc scan without privileges, stdout, process args or env."""
    matches: list[int] = []
    try:
        roots = list(Path("/proc").iterdir())
    except OSError:
        return matches
    for item in roots:
        if not item.name.isdigit():
            continue
        try:
            raw = (item / "cmdline").read_bytes()[:4096]
            if is_realm_8780_command(raw):
                matches.append(int(item.name))
        except (OSError, ValueError):
            continue
    return matches[:8]


def is_ubuntu_uid(pid: int) -> bool | None:
    try:
        import pwd
        target = pwd.getpwnam("ubuntu").pw_uid
        for line in Path(f"/proc/{pid}/status").read_text(encoding="ascii").splitlines():
            if line.startswith("Uid:"):
                return int(line.split()[1]) == target
    except (OSError, KeyError, ValueError, IndexError):
        return None
    return None


def runner_identity_is_ubuntu() -> bool | None:
    try:
        import pwd
        return pwd.getpwnam("ubuntu").pw_uid == os.geteuid()
    except (OSError, KeyError, AttributeError):
        return None


def source_attestation() -> dict:
    state, pid = active_unit_state()
    expected = sha256(EXPECTED)
    listener_pids = public_proc_candidates()
    # A MainPID from a different user manager cannot be treated as the
    # listener identity. Public /proc argv discovery is read-only and bounded.
    observed_pid = pid if pid is not None and pid in listener_pids else (
        listener_pids[0] if len(listener_pids) == 1 else None
    )
    module_candidates: list[Path] = []
    if observed_pid is not None:
        try:
            module_candidates = parse_environ(
                Path(f"/proc/{observed_pid}/environ").read_bytes()
            )
        except OSError:
            pass
        try:
            module_candidates.append(Path(os.readlink(f"/proc/{observed_pid}/cwd")) / MODULE)
        except OSError:
            pass
    candidate_hashes = [sha256(p) for p in dict.fromkeys(module_candidates)]
    candidate_hashes = [h for h in candidate_hashes if h is not None]
    selected = candidate_hashes[0] if candidate_hashes else None
    canonical_checkout = sha256(Path("/home/ubuntu/agentmanager") / MODULE)

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
        "listener_process_detected": bool(listener_pids),
        "single_listener_process_identified": len(listener_pids) == 1,
        "listener_owner_is_ubuntu": is_ubuntu_uid(observed_pid) if observed_pid is not None else None,
        "runner_identity_is_ubuntu": runner_identity_is_ubuntu(),
        "canonical_checkout_matches_expected": (
            canonical_checkout == expected if canonical_checkout and expected else False
        ),
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
