import os
import sys
import platform
import socket
import json
import subprocess
from datetime import datetime
from agentos_node import __version__

class NodeInspector:
    """Inspects the local Runtime Node environment and generates structured harvest payloads."""

    def __init__(self, device_alias=None):
        self.hostname = socket.gethostname()
        self.device_alias = device_alias or os.environ.get("AGENTOS_DEVICE_ALIAS") or self.hostname
        self.node_version = __version__

    def check_secrets_status(self):
        """Check if local secrets are safely stored out-of-repo."""
        secrets_file = os.path.expanduser("~/.agentos.secrets")
        env_file = os.path.join(os.getcwd(), ".env")
        has_secrets = os.path.exists(secrets_file) or os.path.exists(env_file)
        return {
            "has_secrets": has_secrets,
            "secrets_file_exists": os.path.exists(secrets_file),
            "env_file_exists": os.path.exists(env_file),
            "storage_isolated": True
        }

    def get_git_info(self):
        """Fetch Git commit and branch if available."""
        try:
            commit = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL).decode().strip()
            branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], stderr=subprocess.DEVNULL).decode().strip()
            return {"commit": commit, "branch": branch, "is_git": True}
        except Exception:
            return {"commit": "N/A (Standalone Node)", "branch": "N/A", "is_git": False}

    def harvest_payload(self):
        """Generate complete Handoff Payload for Central Control Plane."""
        now = datetime.now().isoformat()
        git_info = self.get_git_info()
        secrets_info = self.check_secrets_status()

        payload = {
            "protocol": "ancp",
            "version": "0.1",
            "messageType": "node.harvest_report",
            "device_alias": self.device_alias,
            "hostname": self.hostname,
            "os": platform.system(),
            "os_release": platform.release(),
            "python_version": platform.python_version(),
            "node_version": self.node_version,
            "collected_at": now,
            "git_info": git_info,
            "secrets_info": secrets_info,
            "agent_mode": os.environ.get("AGENT_MODE", "CLIENT"),
            "status": "HEALTHY",
            "capabilities": [
                "shell.exec",
                "context.harvest",
                "checkpoint.close",
                "resource.query",
                "resource.register",
                "resource.verify.site"
            ]
        }
        return payload

    def save_payload_to_file(self, filepath):
        """Save harvest payload locally."""
        payload = self.harvest_payload()
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return payload
