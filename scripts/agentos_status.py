#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(os.environ.get("AGENTMANAGER_ROOT", os.path.dirname(os.path.dirname(__file__))))
AGENT_DATA_ROOT = Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))
ROLES_DIR = PROJECT_ROOT / ".agent" / "roles"
SPECS_DIR = AGENT_DATA_ROOT / "specs"
MEMORY_ROOT = AGENT_DATA_ROOT / "memory"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent_core import config

KNOWLEDGE_ROOT = config.KNOWLEDGE_DIR

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - optional dependency fallback
    yaml = None

try:
    from agent_core.project_store import list_projects
except Exception:  # pragma: no cover - fallback when project store unavailable
    list_projects = None


@dataclass
class RoleSummary:
    name: str
    kind: str
    skills: list[str]
    memory_read: list[str]
    memory_write: list[str]
    path: str


@dataclass
class ProjectSummary:
    project_id: str
    status: str
    phase: str
    freshness: str
    provided: list[str]
    required: list[str]


@dataclass
class SpecSummary:
    spec: str
    owner: str
    status: str
    targets: list[str]
    notes: list[str]


@dataclass
class MemorySummary:
    name: str
    path: str
    kind: str
    status: str
    size_bytes: int
    item_count: int
    notes: list[str]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def normalize_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def parse_role(path: Path) -> RoleSummary:
    content = read_text(path)
    name = path.stem
    first_heading = next((line.lstrip("# ").strip() for line in content.splitlines() if line.startswith("#")), name)
    kind = path.parent.name

    skills: list[str] = []
    memory_read: list[str] = []
    memory_write: list[str] = []
    active_section: str | None = None
    active_memory_mode: str | None = None
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            active_section = stripped
            active_memory_mode = None
            continue
        if "記憶範圍" in (active_section or "") or "Memory Scope" in (active_section or ""):
            if "讀取" in stripped or "Read Access" in stripped:
                active_memory_mode = "read"
                continue
            if "寫入" in stripped or "Write Access" in stripped:
                active_memory_mode = "write"
                continue
            if stripped.startswith("1.") or stripped.startswith("2.") or stripped.startswith("3.") or stripped.startswith("*") or stripped.startswith("-"):
                item = re.sub(r"^\d+\.\s*", "", stripped)
                item = item.lstrip("*- ").strip()
                if active_memory_mode == "read":
                    memory_read.append(item)
                elif active_memory_mode == "write":
                    memory_write.append(item)
                continue
        if "專業能力" in (active_section or "") or "Skills" in (active_section or ""):
            if stripped.startswith("*") or stripped.startswith("-"):
                item = stripped.lstrip("*- ").strip()
                skills.append(item)

    return RoleSummary(
        name=first_heading,
        kind=kind,
        skills=skills[:8],
        memory_read=memory_read[:8],
        memory_write=memory_write[:8],
        path=str(path),
    )


def collect_roles() -> list[RoleSummary]:
    roles: list[RoleSummary] = []
    if not ROLES_DIR.exists():
        return roles
    for path in sorted(ROLES_DIR.rglob("*.md")):
        try:
            roles.append(parse_role(path))
        except Exception:
            continue
    return roles


def collect_projects() -> list[ProjectSummary]:
    items: list[ProjectSummary] = []
    if list_projects is None:
        return items
    try:
        projects = list_projects()
    except Exception:
        return items

    for project in projects:
        provided = list(getattr(project, "capabilities_provided", []) or [])
        required = list(getattr(project, "capabilities_required", []) or [])
        health = getattr(project, "health", None)
        freshness = getattr(health, "freshness", "unknown") if health else "unknown"
        items.append(
            ProjectSummary(
                project_id=str(getattr(project, "project_id", getattr(project, "name", "unknown"))),
                status=str(getattr(project, "status", "unknown")),
                phase=str(getattr(project, "phase", "unknown")),
                freshness=str(freshness),
                provided=provided,
                required=required,
            )
        )
    items.sort(key=lambda p: p.project_id)
    return items


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    if not content.startswith("---"):
        return {}, content
    lines = content.splitlines()
    end_idx = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break
    if end_idx is None:
        return {}, content
    raw_meta = "\n".join(lines[1:end_idx])
    body = "\n".join(lines[end_idx + 1 :])
    if yaml is None:
        return {}, body
    try:
        meta = yaml.safe_load(raw_meta) or {}
        return meta if isinstance(meta, dict) else {}, body
    except Exception:
        return {}, body


def parse_spec(path: Path) -> SpecSummary:
    content = read_text(path)
    meta, body = parse_frontmatter(content)
    owner = str(meta.get("owner") or "unassigned")
    status = str(meta.get("status") or "unknown")
    targets = normalize_list(meta.get("target_projects") or meta.get("linked_projects"))
    notes: list[str] = []
    if owner == "unassigned":
        notes.append("owner missing")
    if not targets:
        notes.append("targets missing")
    if len(re.findall(r"^\s*-\s+\[ \]\s+", body, flags=re.MULTILINE)):
        notes.append("has open checklist items")
    return SpecSummary(spec=path.stem, owner=owner, status=status, targets=targets, notes=notes)


def collect_specs() -> list[SpecSummary]:
    specs: list[SpecSummary] = []
    if not SPECS_DIR.exists():
        return specs
    for path in sorted(SPECS_DIR.glob("*.md")):
        try:
            specs.append(parse_spec(path))
        except Exception:
            continue
    return specs


def count_files(path: Path, pattern: str = "*") -> int:
    if not path.exists():
        return 0
    return sum(1 for item in path.rglob(pattern) if item.is_file())


def count_dirs(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for item in path.rglob("*") if item.is_dir())


def memory_status_for_file(path: Path, missing_note: str) -> tuple[str, int, list[str]]:
    if not path.exists():
        return "missing", 0, [missing_note]
    size = path.stat().st_size
    notes: list[str] = []
    if size == 0:
        notes.append("empty")
    return "present", size, notes


def collect_memory_systems() -> list[MemorySummary]:
    items: list[MemorySummary] = []

    shared_sync = MEMORY_ROOT / "session_sync.md"
    shared_status, shared_size, shared_notes = memory_status_for_file(shared_sync, "shared sync not found")
    if shared_size > 50_000:
        shared_notes.append("consider compaction")
    items.append(
        MemorySummary(
            name="Shared Memory",
            path=str(shared_sync),
            kind="global sync",
            status=shared_status,
            size_bytes=shared_size,
            item_count=1 if shared_sync.exists() else 0,
            notes=shared_notes,
        )
    )

    memory_root_files = count_files(MEMORY_ROOT, "*.md") + count_files(MEMORY_ROOT, "*.json") + count_files(MEMORY_ROOT, "*.jsonl")
    short_term = MEMORY_ROOT / "SHORT_TERM.md"
    short_status, short_size, short_notes = memory_status_for_file(short_term, "project context not found")
    items.append(
        MemorySummary(
            name="Triple-Layer Context - SHORT_TERM",
            path=str(short_term),
            kind="context",
            status=short_status,
            size_bytes=short_size,
            item_count=1 if short_term.exists() else 0,
            notes=short_notes,
        )
    )

    long_term = MEMORY_ROOT / "LONG_TERM.md"
    long_status, long_size, long_notes = memory_status_for_file(long_term, "history layer not found")
    items.append(
        MemorySummary(
            name="Triple-Layer Context - LONG_TERM",
            path=str(long_term),
            kind="context",
            status=long_status,
            size_bytes=long_size,
            item_count=1 if long_term.exists() else 0,
            notes=long_notes,
        )
    )

    items.append(
        MemorySummary(
            name="Memory Palace Vault",
            path=str(MEMORY_ROOT),
            kind="memory vault",
            status="present" if MEMORY_ROOT.exists() else "missing",
            size_bytes=0,
            item_count=memory_root_files,
            notes=[
                f"{count_dirs(MEMORY_ROOT)} subdirectories discovered",
                "includes archive, snapshots, telegram sessions, and system memory files",
            ] if MEMORY_ROOT.exists() else ["memory root missing"],
        )
    )

    project_memory_root = AGENT_DATA_ROOT / "projects"
    project_memory_dirs = [p for p in project_memory_root.glob("*/memory") if p.exists()]
    project_log_dirs = [p for p in project_memory_root.glob("*/logs") if p.exists()]
    items.append(
        MemorySummary(
            name="Project Memory Bridges",
            path=str(project_memory_root),
            kind="project memory",
            status="present" if project_memory_root.exists() else "missing",
            size_bytes=0,
            item_count=len(project_memory_dirs),
            notes=[
                f"{len(project_memory_dirs)} project memory roots detected",
                f"{len(project_log_dirs)} project log roots detected",
            ] if project_memory_root.exists() else ["project root missing"],
        )
    )

    project_memory_file_count = sum(count_files(p) for p in project_memory_dirs)
    project_log_file_count = sum(count_files(p) for p in project_log_dirs)
    items.append(
        MemorySummary(
            name="Project Memory Payloads",
            path=str(project_memory_root),
            kind="project memory",
            status="present" if project_memory_root.exists() else "missing",
            size_bytes=0,
            item_count=project_memory_file_count + project_log_file_count,
            notes=["memory/md + logs artifacts across projects"] if project_memory_root.exists() else ["project root missing"],
        )
    )

    knowledge_master = KNOWLEDGE_ROOT / "Knowledge_Master_MOC.md"
    knowledge_index = KNOWLEDGE_ROOT / "INDEX.md"
    op_state = KNOWLEDGE_ROOT / "system" / "AgentOS_Operational_State.md"
    knowledge_count = count_files(KNOWLEDGE_ROOT)
    notes = []
    if not knowledge_master.exists():
        notes.append("master MOC missing")
    if not knowledge_index.exists():
        notes.append("knowledge index missing")
    if not op_state.exists():
        notes.append("operational state item missing")
    items.append(
        MemorySummary(
            name="LLM Wiki / Knowledge Palace",
            path=str(KNOWLEDGE_ROOT),
            kind="knowledge base",
            status="present" if KNOWLEDGE_ROOT.exists() else "missing",
            size_bytes=0,
            item_count=knowledge_count,
            notes=notes,
        )
    )

    knowledge_system_dir = KNOWLEDGE_ROOT / "system"
    knowledge_projects_dir = KNOWLEDGE_ROOT / "projects"
    knowledge_history_dir = KNOWLEDGE_ROOT / "history"
    knowledge_logic_dir = KNOWLEDGE_ROOT / "logic"
    items.append(
        MemorySummary(
            name="Knowledge Palace Subtrees",
            path=str(KNOWLEDGE_ROOT),
            kind="knowledge subtrees",
            status="present" if KNOWLEDGE_ROOT.exists() else "missing",
            size_bytes=0,
            item_count=sum(1 for p in [knowledge_system_dir, knowledge_projects_dir, knowledge_history_dir, knowledge_logic_dir] if p.exists()),
            notes=[
                f"system: {count_files(knowledge_system_dir)} files" if knowledge_system_dir.exists() else "system missing",
                f"projects: {count_files(knowledge_projects_dir)} files" if knowledge_projects_dir.exists() else "projects missing",
                f"history: {count_files(knowledge_history_dir)} files" if knowledge_history_dir.exists() else "history missing",
                f"logic: {count_files(knowledge_logic_dir)} files" if knowledge_logic_dir.exists() else "logic missing",
            ] if KNOWLEDGE_ROOT.exists() else ["knowledge root missing"],
        )
    )

    palace_root = MEMORY_ROOT
    palace_notes = []
    archive_dir = palace_root / "archive"
    if not archive_dir.exists():
        palace_notes.append("archive missing")
    palace_items = count_files(palace_root, "*.md")
    items.append(
        MemorySummary(
            name="Archive Vaults",
            path=str(archive_dir),
            kind="archive",
            status="present" if palace_root.exists() else "missing",
            size_bytes=0,
            item_count=count_files(archive_dir, "*.md") + count_files(palace_root / "snapshots", "*.md"),
            notes=palace_notes or ["session archives and snapshots"],
        )
    )

    items.append(
        MemorySummary(
            name="Telegram Session Memory",
            path=str(palace_root / "telegram_sessions"),
            kind="session transcripts",
            status="present" if (palace_root / "telegram_sessions").exists() else "missing",
            size_bytes=0,
            item_count=count_files(palace_root / "telegram_sessions", "*.md"),
            notes=["cross-agent Telegram transcripts"] if (palace_root / "telegram_sessions").exists() else ["telegram sessions missing"],
        )
    )

    runtime_root = AGENT_DATA_ROOT / "runtime"
    items.append(
        MemorySummary(
            name="Runtime Telemetry",
            path=str(runtime_root),
            kind="telemetry",
            status="present" if runtime_root.exists() else "missing",
            size_bytes=0,
            item_count=count_files(runtime_root),
            notes=[
                "pulse_snapshot.json",
                "memory_palace_status.json",
                "ecosystem_sync artifacts",
            ] if runtime_root.exists() else ["runtime root missing"],
        )
    )

    backups_root = AGENT_DATA_ROOT / "backups"
    items.append(
        MemorySummary(
            name="Legacy Backups",
            path=str(backups_root),
            kind="backup vault",
            status="present" if backups_root.exists() else "missing",
            size_bytes=0,
            item_count=count_files(backups_root),
            notes=["environment and state backups"] if backups_root.exists() else ["backups missing"],
        )
    )

    templates_root = AGENT_DATA_ROOT / "templates"
    items.append(
        MemorySummary(
            name="Memory Templates / Seeds",
            path=str(templates_root),
            kind="templates",
            status="present" if templates_root.exists() else "missing",
            size_bytes=0,
            item_count=count_files(templates_root),
            notes=["CLAUDE and bootstrap templates"] if templates_root.exists() else ["templates missing"],
        )
    )

    return items


def memory_health() -> dict[str, Any]:
    sync_path = MEMORY_ROOT / "session_sync.md"
    pulse_path = AGENT_DATA_ROOT / "runtime" / "pulse_snapshot.json"
    return {
        "session_sync_exists": sync_path.exists(),
        "session_sync_bytes": sync_path.stat().st_size if sync_path.exists() else 0,
        "pulse_snapshot_exists": pulse_path.exists(),
        "memory_root_exists": MEMORY_ROOT.exists(),
        "memory_root": str(MEMORY_ROOT),
    }


def build_recommendations(roles: list[RoleSummary], projects: list[ProjectSummary], specs: list[SpecSummary], memory: dict[str, Any]) -> list[str]:
    recs: list[str] = []

    legacy_specs = [s.spec for s in specs if "owner missing" in s.notes or "targets missing" in s.notes]
    if legacy_specs:
        recs.append(f"先補齊 legacy spec 的 frontmatter：{', '.join(legacy_specs[:4])}" + (" ..." if len(legacy_specs) > 4 else ""))

    if any("open checklist items" in s.notes for s in specs):
        recs.append("把還停在 checklist 的 spec 轉成 project task 或 capability task，避免只停留在描述層。")

    proposed_projects = [p.project_id for p in projects if "Proposed" in p.status]
    if proposed_projects:
        recs.append(f"把這些 Proposed 專案推進到可驗證狀態：{', '.join(proposed_projects[:5])}" + (" ..." if len(proposed_projects) > 5 else ""))

    if any(p.project_id == "video-indexing" and "Proposed" in p.status for p in projects):
        recs.append("video-indexing 已是共用核心能力候選，應優先補齊實作任務與驗收條件，盡快從 Proposed 走向 Active。")

    if memory["session_sync_exists"] and memory["session_sync_bytes"] > 50_000:
        recs.append("shared memory / session_sync.md 已經偏大，建議加速 compaction / archive，避免再次吃掉上下文。")

    if any("video-indexing" in p.project_id for p in projects) is False:
        recs.append("video-indexing 是共用能力核心，應盡快確保它在 registry / project store 中穩定可查。")

    if memory.get("knowledge_item_count", 0) < 10:
        recs.append("LLM wiki / Knowledge Palace 的可重用知識條目偏少，建議定期 internalize，補足系統級知識資產。")

    if not memory.get("long_term_exists", False):
        recs.append("三層記憶中的 LONG_TERM 缺失，建議補齊歷史層以承接跨 session 的知識沉澱。")

    if not recs:
        recs.append("目前沒有明顯結構性異常，建議持續跑 /ecosystem-report 與 /spec-steward 維持節奏。")

    return recs


def render_markdown(
    roles: list[RoleSummary],
    projects: list[ProjectSummary],
    specs: list[SpecSummary],
    memories: list[MemorySummary],
    memory: dict[str, Any],
    recs: list[str],
) -> str:
    role_rows = "\n".join(
        f"| **{r.name}** | {r.kind} | {', '.join(r.skills[:3]) or '—'} | {', '.join(r.memory_read[:2]) or '—'} | {', '.join(r.memory_write[:2]) or '—'} |"
        for r in roles
    ) or "| — | — | — | — | — |"

    project_rows = "\n".join(
        f"| **{p.project_id}** | {p.status} | {p.phase} | {p.freshness} | {', '.join(p.provided[:3]) or '—'} | {', '.join(p.required[:3]) or '—'} |"
        for p in projects
    ) or "| — | — | — | — | — | — |"

    spec_rows = "\n".join(
        f"| **{s.spec}** | {s.status} | {s.owner} | {', '.join(s.targets) or '—'} | {', '.join(s.notes) or '—'} |"
        for s in specs
    ) or "| — | — | — | — | — |"

    lines = [
        "# 🌐 AgentOS Status Center",
        "",
        f"- **Generated**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"- **Roles**: {len(roles)}",
        f"- **Projects**: {len(projects)}",
        f"- **Specs**: {len(specs)}",
        f"- **Proposed Projects**: {len([p for p in projects if 'Proposed' in p.status])}",
        f"- **Legacy / Unstructured Specs**: {len([s for s in specs if 'owner missing' in s.notes or 'targets missing' in s.notes])}",
        "",
        "## ⚠️ Watchlist",
        *([f"- {item}" for item in recs[:4]] if recs else ["- —"]),
        "",
        "## 🧠 Memory Systems",
        "| System | Kind | Status | Items | Size | Notes |",
        "| :--- | :--- | :--- | :---: | :---: | :--- |",
    ]
    for mem in memories:
        note_text = ", ".join(mem.notes) if mem.notes else "—"
        size_text = f"{mem.size_bytes} B" if mem.size_bytes else "—"
        lines.append(f"| **{mem.name}** | {mem.kind} | {mem.status} | {mem.item_count} | {size_text} | {note_text} |")

    lines.extend([
        "",
        "## 👥 Roles",
        "| Role | Kind | Skills | Memory Read | Memory Write |",
        "| :--- | :--- | :--- | :--- | :--- |",
        role_rows,
        "",
        "## 🧩 Projects",
        "| Project | Status | Phase | Freshness | Provided | Required |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
        project_rows,
        "",
        "## 📐 Specs",
        "| Spec | Status | Owner | Targets | Notes |",
        "| :--- | :--- | :--- | :--- | :--- |",
        spec_rows,
        "",
        "## 🧠 Memory Health",
        f"- `session_sync.md`: {'present' if memory['session_sync_exists'] else 'missing'}",
        f"- `session_sync.md` size: {memory['session_sync_bytes']} bytes",
        f"- `pulse_snapshot.json`: {'present' if memory['pulse_snapshot_exists'] else 'missing'}",
        f"- `memory/`: {'present' if memory['memory_root_exists'] else 'missing'}",
        "",
        "## 🔎 Improvement Directions",
    ])
    lines.extend([f"- {item}" for item in recs])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a consolidated AgentOS status report.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of markdown.")
    args = parser.parse_args()

    roles = collect_roles()
    projects = collect_projects()
    specs = collect_specs()
    memories = collect_memory_systems()
    memory = memory_health()
    memory["knowledge_item_count"] = next((m.item_count for m in memories if m.name == "LLM Wiki / Knowledge Palace"), 0)
    memory["long_term_exists"] = (MEMORY_ROOT / "LONG_TERM.md").exists()
    recs = build_recommendations(roles, projects, specs, memory)

    if args.json:
        print(json.dumps({
            "roles": [asdict(r) for r in roles],
            "projects": [asdict(p) for p in projects],
            "specs": [asdict(s) for s in specs],
            "memory_systems": [asdict(m) for m in memories],
            "memory": memory,
            "recommendations": recs,
        }, ensure_ascii=False, indent=2))
        return 0

    print(render_markdown(roles, projects, specs, memories, memory, recs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
