#!/usr/bin/env python3
"""Sanitized read-only proof of the *effective* Realm Fabric process source.

No raw systemd unit, drop-ins, env, cmdline, journal, config, tokens or
filesystem paths are emitted. This does not start/restart/modify a service.
"""
from __future__ import annotations
import hashlib
import json
import os
import pwd
from pathlib import Path
import re
import subprocess
import sys

CHECKOUT = Path("/home/ubuntu/agentmanager")
RELEASE_POINTER = Path("/home/ubuntu/.local/share/agentos/realm-fabric/current")
EXPECTED_SYMBOL = "_GITHUB_MAIN_RUNTIME_REPAIR_WORKFLOW_REF"
SERVICE = "agentos-realm-fabric.service"
PROVENANCE = Path("/home/ubuntu/agent-data/runtime/realm-fabric/provenance.json")
SHA = re.compile(r"[a-f0-9]{40}\Z")


def classify_path(path: Path | None, *, checkout: Path, release: Path) -> str:
    if path is None:
        return "unknown"
    try:
        resolved = path.resolve(strict=True)
        if resolved == checkout.resolve(strict=True):
            return "checkout"
        if resolved == release.resolve(strict=True):
            return "immutable_realm_release"
    except (OSError, ValueError, RuntimeError):
        return "unknown"
    return "other"


def source_state(path: Path) -> dict[str, object]:
    try:
        raw = (path / "agent_core/realm_server.py").read_bytes()
    except (OSError, ValueError):
        return {"readable": False, "repair_carrier_oidc_present": False}
    return {
        "readable": True,
        "repair_carrier_oidc_present": EXPECTED_SYMBOL.encode("utf-8") in raw,
        "realm_server_sha256": hashlib.sha256(raw).hexdigest(),
    }


# Allowlisted production roots only; a systemd unit cannot make an
# arbitrary absolute path available for introspection through this audit.
_APPROVED_SOURCE_ROOTS = (
    Path("/home/ubuntu/agentmanager"),
    Path("/home/ubuntu/agent-data"),
    Path("/home/ubuntu/.local/share/agentos/realm-fabric"),
    Path("/home/agentos-node/.local/share/agentos/realm-fabric"),
)

def observed_workdir_source(path: Path | None) -> dict[str, object]:
    """Return only a fixed-code-file hash and OIDC-presence bit, never path/text."""
    failure = {"approved_root": False, "source_readable": False,
               "oidc_repair_carrier_present": False, "source_sha256": None}
    if path is None:
        return failure
    try:
        resolved = path.resolve(strict=True)
        approved = any(resolved == root or resolved.is_relative_to(root)
                       for root in _APPROVED_SOURCE_ROOTS)
        if not approved:
            return failure
        source = source_state(resolved)
        return {"approved_root": True,
                "source_readable": bool(source.get("readable")),
                "oidc_repair_carrier_present": bool(source.get("repair_carrier_oidc_present")),
                "source_sha256": source.get("realm_server_sha256")}
    except (OSError, ValueError, RuntimeError):
        return failure


def get_service_state() -> dict[str, object]:
    try:
        p = subprocess.run([
            "/usr/bin/systemctl", "--user", "show", SERVICE,
            "-p", "MainPID", "-p", "ActiveState", "-p", "WorkingDirectory",
            "-p", "ExecStart", "--no-pager",
        ], capture_output=True, text=True, timeout=8, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False, "active": False, "pid_present": False}
    if p.returncode:
        return {"available": False, "active": False, "pid_present": False}
    props = dict(line.split("=", 1) for line in p.stdout.splitlines() if "=" in line)
    pid_value = props.get("MainPID") or ""
    pid = int(pid_value) if pid_value.isdigit() else 0
    root = Path(props["WorkingDirectory"]) if props.get("WorkingDirectory", "").startswith("/") else None
    try:
        proc_cwd = Path(f"/proc/{pid}/cwd").resolve(strict=True) if pid > 1 else None
    except (OSError, ValueError, RuntimeError):
        proc_cwd = None
    return {
        "available": True,
        "active": props.get("ActiveState") == "active",
        "pid_present": pid > 1,
        "working_directory_class": classify_path(root, checkout=CHECKOUT, release=RELEASE_POINTER),
        "process_cwd_class": classify_path(proc_cwd, checkout=CHECKOUT, release=RELEASE_POINTER),
        "execstart_realm_module": "agent_core.realm_cli" in (props.get("ExecStart") or ""),
        "configured_workdir_source": observed_workdir_source(root),
        "process_cwd_source": observed_workdir_source(proc_cwd),
        "configured_process_source_agree": (
            observed_workdir_source(root).get("source_sha256") is not None
            and observed_workdir_source(root).get("source_sha256")
                == observed_workdir_source(proc_cwd).get("source_sha256")
        ),
    }


def bounded_realm_process_candidates() -> dict[str, object]:
    """Find likely Realm process owner, never emit PID, argv or personal paths.

    This is NOT authoritative port-to-process evidence. Do not declare the
    process on 8780 identified merely because its command matches the service.
    """
    owners: set[str] = set()
    roots: set[str] = set()
    count = 0
    try:
        candidates = list(Path("/proc").iterdir())[:8192]
    except OSError:
        candidates = []
    for entry in candidates:
        if not entry.name.isdigit():
            continue
        try:
            raw = (entry / "cmdline").read_bytes()[:4096]
            argv = raw.split(b"\0")
            # A precise module + serve pair; do not match arbitrary shell
            # snippets, process supervisors or test command arguments.
            if not any(v == b"agent_core.realm_cli" for v in argv):
                continue
            if b"serve" not in argv:
                continue
            count += 1
            user = pwd.getpwuid(entry.stat().st_uid).pw_name
            owners.add(user if user in ("ubuntu", "agentos-node") else "other")
            try:
                roots.add(classify_path((entry / "cwd").resolve(strict=True),
                       checkout=CHECKOUT, release=RELEASE_POINTER))
            except (OSError, ValueError, RuntimeError):
                roots.add("unknown")
        except (OSError, ValueError, KeyError):
            continue
    return {
        "candidate_process_detected": count > 0,
        "candidate_count_band": "none" if count == 0 else "one" if count == 1 else "multiple",
        "candidate_owner_class": next(iter(owners)) if len(owners) == 1 else "multiple" if owners else "unknown",
        "candidate_workdir_class": next(iter(roots)) if len(roots) == 1 else "multiple" if roots else "unknown",
        "candidate_owns_8780_proved": False,
    }


def current_release_commit() -> str | None:
    try:
        release = RELEASE_POINTER.resolve(strict=True)
        if release == CHECKOUT.resolve(strict=True):
            return None
        p = subprocess.run(["/usr/bin/git", "-C", str(release), "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=6, check=False)
        val = p.stdout.strip()
        return val if p.returncode == 0 and SHA.fullmatch(val) else None
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
        return None


def source_provenance() -> str | None:
    try:
        value = json.loads(PROVENANCE.read_text(encoding="utf-8")).get("source_commit")
        return value if isinstance(value, str) and SHA.fullmatch(value) else None
    except (OSError, ValueError, TypeError):
        return None


def inspect() -> dict[str, object]:
    service = get_service_state()
    processes = bounded_realm_process_candidates()
    checkout = source_state(CHECKOUT)
    release = source_state(RELEASE_POINTER)
    active = bool(service.get("active"))
    effective_from_release = service.get("working_directory_class") == "immutable_realm_release"
    effective_from_checkout = service.get("working_directory_class") == "checkout"
    loaded_candidate = release if effective_from_release else checkout if effective_from_checkout else None
    same_file = bool(
        checkout.get("readable") and release.get("readable")
        and checkout.get("realm_server_sha256") == release.get("realm_server_sha256")
    )
    loaded_oidc = bool(loaded_candidate and loaded_candidate.get("repair_carrier_oidc_present"))
    # A unit may legitimately load from a pinned release unrelated to either
    # symbolic root. Compare only the approved effective WorkingDirectory and
    # candidate process CWD sources; never infer in-memory import.
    workdir = service.get("configured_workdir_source") or {}
    process_workdir = service.get("process_cwd_source") or {}
    effective_oidc = bool(workdir.get("oidc_repair_carrier_present"))
    effective_source_readable = bool(workdir.get("source_readable"))

    classification = (
        "REALM_SERVICE_UNAVAILABLE" if not active else
        "REALM_EFFECTIVE_SOURCE_OIDC_ABSENT" if effective_source_readable and not effective_oidc else
        "REALM_EFFECTIVE_UNIT_UNKNOWN" if not (effective_from_release or effective_from_checkout) else
        "REALM_LOADED_OIDC_CARRIER_ABSENT" if not loaded_oidc else
        "REALM_LOADED_SOURCE_MATCHES_EXPECTED"
    )
    return {
        "schema": "agentos.realm-effective-runtime-audit/v1",
        "read_only": True,
        "service": service,
        "realm_process_candidates": processes,
        "runner_user_service_mismatch_suspected": (
            not service.get("available")
            and processes["candidate_owner_class"] == "agentos-node"
        ),
        "checkout": checkout,
        "realm_immutable_release": release,
        "checkout_release_identical": same_file,
        "configured_provenance_commit": source_provenance(),
        "current_immutable_release_commit": current_release_commit(),
        "loaded_oidc_carrier_visible_on_disk": loaded_oidc,
        "effective_workdir_oidc_carrier_visible_on_disk": effective_oidc,
        "effective_workdir_source_readable": effective_source_readable,
        "classification": classification,
        # This is an on-disk/effective-unit observation, NOT proof of the
        # exact Python objects already imported by an active process.
        "in_memory_module_proven": False,
        "production_mutations": False,
    }


def main() -> int:
    result = inspect()
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0 if result["classification"] == "REALM_LOADED_SOURCE_MATCHES_EXPECTED" else 2


if __name__ == "__main__":
    sys.exit(main())
