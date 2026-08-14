#!/usr/bin/env python3
"""
Clean up stale Claude Code artifacts (shell-snapshots and session-env files)
to prevent disk space growth and session tracking conflicts.

Keeps only files modified within the last N_DAYS.
"""
import os
import time
from pathlib import Path

HOME = Path.home()
CLAUDE_DIR = HOME / ".claude"
SHELL_SNAPSHOTS = CLAUDE_DIR / "shell-snapshots"
SESSION_ENV = CLAUDE_DIR / "session-env"
SESSIONS = CLAUDE_DIR / "sessions"

RETENTION_DAYS = 3
KEEP_SESSION_JSON = 5  # Keep at most N active session JSON files (PIDs)

CUTOFF = time.time() - (RETENTION_DAYS * 86400)

def cleanup_dir(dirpath, pattern, keep_count=None):
    """Remove files older than retention period. If keep_count is set, also keep the N newest."""
    if not dirpath.exists():
        return 0
    files = sorted(dirpath.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)
    removed = 0
    for f in files:
        if keep_count is not None and keep_count > 0:
            keep_count -= 1
            continue
        if f.stat().st_mtime < CUTOFF:
            try:
                f.unlink()
                removed += 1
            except OSError:
                pass
    return removed

def cleanup_session_json():
    """Keep only the N most recent session JSON files."""
    if not SESSIONS.exists():
        return 0
    jsons = sorted(SESSIONS.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    removed = 0
    for j in jsons[KEEP_SESSION_JSON:]:
        try:
            j.unlink()
            removed += 1
        except OSError:
            pass
    return removed

def main():
    removed_snapshots = cleanup_dir(SHELL_SNAPSHOTS, "snapshot-bash-*.sh")
    removed_env = cleanup_dir(SESSION_ENV, "*.json")
    removed_sessions = cleanup_session_json()
    total = removed_snapshots + removed_env + removed_sessions
    if total > 0:
        print(f"[Claude Code Cleanup] Removed {total} stale files "
              f"(snapshots: {removed_snapshots}, env: {removed_env}, sessions: {removed_sessions})")
    else:
        print("[Claude Code Cleanup] Nothing to clean up.")

if __name__ == "__main__":
    main()
