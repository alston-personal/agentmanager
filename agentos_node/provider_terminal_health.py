"""Shared provider terminal-auth decision; retained across restarts, invalidated by runtime/auth changes."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

TERMINAL_OAUTH_CLASS = "OAUTH_CLIENT_UNSUPPORTED"


def gemini_identity(executable: str | Path, *, home: Path | None = None) -> str:
    binary = Path(executable).resolve()
    stat = binary.stat()
    home = home or Path.home()
    auth = "oauth-personal"
    settings = home / ".gemini" / "settings.json"
    if settings.is_file():
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
            auth = str(((data.get("security") or {}).get("auth") or {}).get("selectedType") or auth)
        except (OSError, ValueError, TypeError, AttributeError):
            pass
    payload = {"path": str(binary), "size": stat.st_size,
               "mtimeNs": stat.st_mtime_ns, "authType": auth}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def breaker_path(*, data_root: Path | None = None) -> Path:
    root = data_root or Path(os.environ.get("AGENT_DATA_ROOT", str(Path.home() / "agent-data")))
    return root / "provider_health" / "gemini-cli" / "oauth-client-terminal.json"


def blocked(identity: str, *, data_root: Path | None = None) -> bool:
    try:
        target = breaker_path(data_root=data_root)
        if target.is_symlink():
            return False
        record = json.loads(target.read_text(encoding="utf-8"))
        return (record.get("schema") == "agentos.provider-terminal-health/v1"
                and record.get("identity") == identity
                and record.get("classification") == TERMINAL_OAUTH_CLASS)
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def record_block(identity: str, *, data_root: Path | None = None) -> None:
    target = breaker_path(data_root=data_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        raise RuntimeError("terminal health path is a symlink")
    record = {"schema": "agentos.provider-terminal-health/v1", "provider": "gemini-cli",
              "identity": identity, "classification": TERMINAL_OAUTH_CLASS,
              "routable": False, "retryPolicy": "require_runtime_or_auth_method_change",
              "observedAtUnix": int(time.time())}
    with tempfile.NamedTemporaryFile(mode="w", dir=target.parent, encoding="utf-8", delete=False) as file:
        json.dump(record, file, sort_keys=True)
        file.write("\n")
        staged = Path(file.name)
    os.chmod(staged, 0o600)
    os.replace(staged, target)
