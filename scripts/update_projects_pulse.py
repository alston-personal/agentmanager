#!/usr/bin/env python3
"""
update_projects_pulse.py - Aggregates project states into a high-speed JSON cache.

STATUS.md remains descriptive evidence. When a project has a reachable local
workspace, the pulse also publishes an execution-head receipt so a newer local
Git head is not hidden by an older remote branch or STATUS.md summary.
"""

import json
import re
import sys
from dataclasses import asdict
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent_core.memory_router import resolve_memory_route
from agent_core.platform import get_platform_driver
from scripts.execution_head import collect_execution_head, arbitrate_heads

route = resolve_memory_route()
AGENT_DATA_ROOT = route.data_root
PROJECTS_DIR = AGENT_DATA_ROOT / "projects"

PLATFORM_DRIVER = get_platform_driver(project_root=PROJECT_ROOT, data_root=AGENT_DATA_ROOT)
SHM_ROOT = PLATFORM_DRIVER.volatile_state_dir()
SHM_PULSE = SHM_ROOT / "projects_pulse.json"
PERSISTENT_PULSE = PLATFORM_DRIVER.persistent_state_dir() / "projects_pulse_snapshot.json"
EXECUTION_HEAD_FILENAME = "execution-head.json"


def parse_status_md(status_path: Path) -> dict:
    data = {
        "priority": 99,
        "category": "unknown",
        "lifecycle_stage": "unknown",
        "tags": [],
        "last_status": "Unknown",
        "last_updated": "Unknown",
        "pending_todos": 0,
    }
    if not status_path.exists():
        return data

    content = status_path.read_text(encoding="utf-8")
    fm_match = re.search(r"^---\n(.*?)\n---", content, re.DOTALL)
    if fm_match:
        fm = fm_match.group(1)
        for line in fm.split("\n"):
            if line.startswith("priority:"):
                try:
                    data["priority"] = int(line.split(":", 1)[1].strip())
                except Exception:
                    pass
            elif line.startswith("category:"):
                data["category"] = line.split(":", 1)[1].strip()
            elif line.startswith("lifecycle_stage:"):
                data["lifecycle_stage"] = line.split(":", 1)[1].strip()

    for line in content.split("\n"):
        if "| **Last Status**" in line:
            parts = line.split("|")
            if len(parts) >= 3:
                data["last_status"] = parts[2].strip()
        elif "| **Last Updated**" in line:
            parts = line.split("|")
            if len(parts) >= 3:
                data["last_updated"] = parts[2].strip()

    todo_match = re.search(r"## 📅 Todo List\n(.*)", content, re.DOTALL)
    if todo_match:
        todos = todo_match.group(1).split("\n")
        data["pending_todos"] = len([t for t in todos if t.strip().startswith("- [ ]")])
    return data


def status_evidence(status_path: Path, status: dict) -> dict:
    try:
        observed = datetime.fromtimestamp(status_path.stat().st_mtime, tz=timezone.utc).isoformat()
    except OSError:
        observed = datetime.fromtimestamp(0, tz=timezone.utc).isoformat()
    return {
        "source": "status-md",
        "observed_at": observed,
        "version": None,
        "status": status.get("last_status"),
        "updated_label": status.get("last_updated"),
    }


def load_execution_receipt(project_dir: Path) -> dict | None:
    target = project_dir / EXECUTION_HEAD_FILENAME
    if not target.exists():
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not data.get("local_head"):
            return None
        data = dict(data)
        data["source"] = "execution-receipt"
        return data
    except Exception:
        return None


def publish_execution_receipt(project_dir: Path, execution: dict) -> None:
    """Publish only meaningful local evidence into the project data layer.

    Workspace-not-found is still present in the aggregate pulse but does not
    overwrite a previously valid execution receipt.
    """
    if execution.get("error") or not execution.get("local_head"):
        return
    target = project_dir / EXECUTION_HEAD_FILENAME
    target.write_text(json.dumps(execution, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    SHM_ROOT.mkdir(parents=True, exist_ok=True)
    PERSISTENT_PULSE.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).isoformat()
    pulse_data = {
        "schema": "agentos.projects-pulse/v2",
        "timestamp": timestamp,
        "projects": {},
    }

    if PROJECTS_DIR.exists():
        for proj_dir in PROJECTS_DIR.iterdir():
            if not proj_dir.is_dir():
                continue
            status_file = proj_dir / "STATUS.md"
            if not status_file.exists():
                continue

            status = parse_status_md(status_file)
            persisted_receipt = load_execution_receipt(proj_dir)
            execution = asdict(collect_execution_head(proj_dir.name, proj_dir))
            publish_execution_receipt(proj_dir, execution)

            evidence = [execution]
            if persisted_receipt:
                evidence.append(persisted_receipt)
            evidence.append(status_evidence(status_file, status))
            arbitration = arbitrate_heads(evidence)

            pulse_data["projects"][proj_dir.name] = {
                **status,
                "execution": execution,
                "persisted_execution_receipt": persisted_receipt,
                "resolved_head": arbitration.get("winner"),
                "state_conflicts": arbitration.get("conflicts", []),
                "invalid_evidence": arbitration.get("invalid_evidence", []),
                "resolution_reason": arbitration.get("reason"),
            }

    json_data = json.dumps(pulse_data, ensure_ascii=False, indent=2)
    SHM_PULSE.write_text(json_data, encoding="utf-8")
    PERSISTENT_PULSE.write_text(json_data, encoding="utf-8")

    valid_heads = sum(
        1 for item in pulse_data["projects"].values()
        if (item.get("resolved_head") or {}).get("local_head")
    )
    print(f"✅ Pulse updated: {len(pulse_data['projects'])} projects cached; {valid_heads} resolved execution heads available.")


if __name__ == "__main__":
    main()
