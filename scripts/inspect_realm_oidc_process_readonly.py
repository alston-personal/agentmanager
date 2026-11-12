#!/usr/bin/env python3
"""Unprivileged, read-only Realm Fabric process/source provenance inspection.

This diagnostic cannot prove Python's in-memory module identity; it records
only a sanitized file + service + process-CWD correlation. It never displays
service Environment, cmdline, source text, stderr, tokens, or raw unit config.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

REPO = Path("/home/ubuntu/agentmanager")
SERVICE = "agentos-realm-fabric.service"
SOURCE = "agent_core/realm_server.py"
EXPECTED_CARRIER = "main-action-runtime-migration-20261007.yml"


def _fixed(argv: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, timeout=10, check=False)


def inspect(expected_commit: str) -> dict:
    if not re.fullmatch(r"[a-f0-9]{40}", expected_commit):
        raise ValueError("exact_commit_required")
    status = {
        "schema": "agentos.realm-oidc-source-attestation/v1",
        "read_only": True,
        "process_observed": False,
        "process_cwd_matches_canonical": False,
        "installed_file_readable": False,
        "installed_matches_expected_commit": False,
        "source_allows_exact_main_repair": False,
        "authoritative_loaded_module_proved": False,
        "result": "BLOCKED",
    }
    try:
        pid_run = _fixed(["/usr/bin/systemctl", "--user", "show", SERVICE, "--property=MainPID", "--value"])
        if pid_run.returncode == 0:
            pid_raw = pid_run.stdout.decode("ascii", errors="ignore").strip()
            if re.fullmatch(r"[1-9][0-9]{0,8}", pid_raw):
                pid = int(pid_raw)
                cwd = Path(f"/proc/{pid}/cwd")
                status["process_observed"] = cwd.exists()
                try:
                    status["process_cwd_matches_canonical"] = cwd.resolve(strict=True) == REPO
                except (OSError, ValueError):
                    pass

        live = REPO / SOURCE
        observed = live.read_bytes()
        status["installed_file_readable"] = True
        fetched = _fixed(["/usr/bin/git", "-C", str(REPO), "show", f"{expected_commit}:{SOURCE}"])
        if fetched.returncode == 0:
            status["installed_matches_expected_commit"] = hashlib.sha256(observed).digest() == hashlib.sha256(fetched.stdout).digest()
        # Recognize the exact bounded workflow contract, not only a generic main-ref rule.
        text = observed.decode("utf-8")
        status["source_allows_exact_main_repair"] = (
            EXPECTED_CARRIER in text
            and "_GITHUB_MAIN_RUNTIME_REPAIR_WORKFLOW_REF" in text
            and "main_runtime_repair_carrier" in text
        )
    except (OSError, UnicodeError, subprocess.TimeoutExpired):
        pass

    # Disk/process-CWD evidence is NOT proof of already-imported code or effective
    # live Gateway generation, hence never upgrade this into a release receipt.
    if not status["process_observed"]:
        status["classification"] = "REALM_PROCESS_UNOBSERVED"
    elif not status["process_cwd_matches_canonical"]:
        status["classification"] = "REALM_PROCESS_SOURCE_ROOT_MISMATCH"
    elif not status["installed_file_readable"]:
        status["classification"] = "REALM_SOURCE_UNREADABLE"
    elif not status["source_allows_exact_main_repair"]:
        status["classification"] = "REALM_SOURCE_OIDC_CARRIER_STALE"
    elif not status["installed_matches_expected_commit"]:
        status["classification"] = "REALM_SOURCE_COMMIT_MISMATCH"
    else:
        status["classification"] = "REALM_DISK_MATCHES_BUT_LOADED_MODULE_UNVERIFIED"
    return status


def main() -> int:
    if len(sys.argv) != 2:
        return 2
    try:
        result = inspect(sys.argv[1])
    except ValueError:
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
