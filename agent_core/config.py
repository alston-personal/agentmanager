from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(
    os.environ.get("AGENT_PROJECT_ROOT", Path(__file__).resolve().parents[1])
).expanduser().resolve()


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = os.path.expandvars(value.strip().strip('"').strip("'"))
        os.environ.setdefault(key, value)


_load_env_file(PROJECT_ROOT / ".env")

HOME = Path.home()
AGENT_DATA_ROOT = Path(
    os.environ.get("AGENT_DATA_ROOT")
    or os.environ.get("AGENT_DATA_DIR")
    or HOME / "agent-data"
).expanduser()
AGENT_DATA_DIR = AGENT_DATA_ROOT
WORKSPACE_NAME = os.environ.get("WORKSPACE_NAME", os.uname().nodename)
AGENT_MODE = os.environ.get("AGENT_MODE", "CLIENT")

PROJECTS_DIR = AGENT_DATA_ROOT / "projects"
MEMORY_DIR = AGENT_DATA_ROOT / "memory"
RUNTIME_DIR = AGENT_DATA_ROOT / "runtime"
LOGS_DIR = AGENT_DATA_ROOT / "logs"
KNOWLEDGE_DIR = AGENT_DATA_ROOT / "knowledge"

