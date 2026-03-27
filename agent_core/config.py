"""
agent_core/config.py
Central configuration and path resolution for Agent OS.
"""
import os
from pathlib import Path


PROJECT_ROOT = Path(os.environ.get("AGENTMANAGER_ROOT", "/home/ubuntu/agentmanager"))
AGENT_DATA_ROOT = Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))
WORKSPACE_NAME = os.environ.get("WORKSPACE_NAME", "default-workspace")

# Data layer paths
CENTRAL_PROJECTS_DIR = AGENT_DATA_ROOT / "projects"
MEMORY_DIR = AGENT_DATA_ROOT / "memory"
JOURNALS_DIR = AGENT_DATA_ROOT / "journals"
RUNTIME_DIR = AGENT_DATA_ROOT / "runtime"

# Logic layer paths
WORKFLOWS_DIR = PROJECT_ROOT / ".agent" / "workflows"
SKILLS_DIR = PROJECT_ROOT / ".agent" / "skills"
SCHEMAS_DIR = PROJECT_ROOT / "rules" / "schemas"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

# Agent communication
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")

# LCS Shared Memory (volatile, for real-time agent comms)
LCS_SHM_ROOT = Path("/dev/shm/leopardcat-swarm")
LCS_PULSE_FILE = LCS_SHM_ROOT / "pulse.json"
LCS_EVENTS_LOG = LCS_SHM_ROOT / "events.log"

# Persistent event log base
EVENTS_JSONL_NAME = "events.jsonl"


def load_env(env_file: Path | None = None) -> None:
    """Load .env file into os.environ."""
    env_path = env_file or (PROJECT_ROOT / ".env")
    if not env_path.exists():
        return
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


# Auto-load on import
load_env()
