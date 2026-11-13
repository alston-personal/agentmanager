#!/usr/bin/env python3
"""Read-only active Dashboard owner-identity configuration probe for #2198.

Does not authenticate a user, grant roles, print allowlist contents or read cookies.
Validates effective configuration under the serving process UID, not the SSH user's HOME.
"""
from __future__ import annotations

import argparse
import os
import pwd
import re
import stat
import subprocess
from pathlib import Path


def process_pids_on_port(port: int, ss_output: str) -> set[int]:
    return {int(value) for value in re.findall(r"\bpid=(\d+)\b", ss_output)}


def safe_private_identities(home: Path, uid: int) -> tuple[set[str], str]:
    file = home / ".config" / "milkcat" / "admin-identities"
    try:
        details = file.lstat()
        if not stat.S_ISREG(details.st_mode) or details.st_uid != uid or details.st_mode & 0o077:
            return set(), "REJECTED"
        return {i.strip().lower() for i in re.split(r"[\r\n,]+", file.read_text(encoding="utf-8")) if i.strip()}, "PASS"
    except FileNotFoundError:
        return set(), "MISSING"
    except (OSError, UnicodeError):
        return set(), "UNREADABLE"


def inspect_process(proc: Path, identity: str) -> dict[str, str]:
    try:
        status = (proc / "status").read_text(encoding="utf-8")
        uid_line = next(row for row in status.splitlines() if row.startswith("Uid:"))
        uid = int(uid_line.split()[1])  # effective UID
        home = Path(pwd.getpwuid(uid).pw_dir)
        file_members, file_state = safe_private_identities(home, uid)
        raw = (proc / "environ").read_bytes()
        env_members = set()
        for part in raw.split(b"\0"):
            if part.startswith(b"MILKCAT_ADMIN_IDENTITIES="):
                env_members.update(x.strip().lower() for x in part.split(b"=", 1)[1].decode("utf-8").split(",") if x.strip())
        return {
            "private_file": file_state,
            "identity_configured": "PASS" if identity.lower() in (file_members | env_members) else "MISSING",
            "process_inspected": "PASS",
            "session_role_attested": "NO",
        }
    except (OSError, ValueError, StopIteration, KeyError, UnicodeError):
        return {"private_file": "UNKNOWN", "identity_configured": "UNKNOWN",
                "process_inspected": "UNKNOWN", "session_role_attested": "NO"}


def inspect_active_dashboard(port: int, identity: str) -> dict[str, str]:
    try:
        output = subprocess.check_output(
            ["ss", "-H", "-ltnp", f"sport = :{port}"], text=True, timeout=4
        )
        pids = process_pids_on_port(port, output)
        if len(pids) != 1:
            return {"process_inspected": "UNKNOWN", "identity_configured": "UNKNOWN",
                    "private_file": "UNKNOWN", "session_role_attested": "NO"}
        pid = next(iter(pids))
        return inspect_process(Path("/proc") / str(pid), identity)
    except (subprocess.SubprocessError, OSError):
        return {"process_inspected": "UNKNOWN", "identity_configured": "UNKNOWN",
                "private_file": "UNKNOWN", "session_role_attested": "NO"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--active-port", type=int, choices=[3040, 3041], required=True)
    parser.add_argument("--identity", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"google:username:[a-z0-9._%+-]+@milkcat\.org", args.identity):
        parser.error("unsupported identity format")
    result = inspect_active_dashboard(args.active_port, args.identity)
    for name, value in sorted(result.items()):
        print(f"agentos_admin_{name}={value}")
    return 0  # Evidence-only; missing owner config must not bypass/rollback release.


if __name__ == "__main__":
    raise SystemExit(main())
