"""
actions/task.py
Task State Machine Orchestrator for Agent OS.

Replaces the markdown `- [ ]` checkbox approach with a formal task registry.
Currently modifies `SHORT_TERM.md` safely by replacing the status of the matching task,
and eventually will sync with `task.schema.json`.
"""
from __future__ import annotations

import re
from pathlib import Path

from agent_core.context import RuntimeContext
from agent_core.registry import registry, ActionResult
from agent_core.config import CENTRAL_PROJECTS_DIR
from agent_core.project_store import load_project
from agent_memory.event_store import emit as emit_event


@registry.register(
    "task",
    description="Manage project task status (todo, in_progress, blocked, done)",
    aliases=["t"],
    requires_project=False,
)
def handle_task(ctx: RuntimeContext) -> ActionResult:
    """
    Update a task status or list tasks.
    Usage:
      /task ls
      /task update "Add README" done
    """
    if len(ctx.args) == 0:
        return ActionResult.fail("Usage: /task ls  OR  /task update <task_text> <status>")

    subcmd = ctx.args[0]
    
    project_id = ctx.project_id or _infer_project_from_cwd()
    if not project_id:
        return ActionResult.fail("Cannot determine project. Use --project <id>")

    memory_dir = CENTRAL_PROJECTS_DIR / project_id / "memory"
    short_term_path = memory_dir / "SHORT_TERM.md"

    if not short_term_path.exists():
        # Fallback to logic repo
        project = load_project(project_id)
        if project and Path(project.actual_code_path).joinpath("memory", "SHORT_TERM.md").exists():
            short_term_path = Path(project.actual_code_path).joinpath("memory", "SHORT_TERM.md")
        else:
            return ActionResult.fail(f"No SHORT_TERM.md found for project {project_id}.")

    if subcmd == "ls":
        tasks = _extract_all_tasks(short_term_path)
        if not tasks:
            return ActionResult.ok("No tasks found.")
        
        lines = [f"## Tasks for {project_id}"]
        for status, text in tasks:
            icon = "✅" if status == "x" else "⬜"
            lines.append(f"{icon} {text}")
        return ActionResult.ok("\n".join(lines))

    if subcmd == "update" and len(ctx.args) >= 3:
        target_text = ctx.args[1]
        new_status = ctx.args[2] # "todo" or "done"
        
        checkbox_char = "x" if new_status.lower() in ("done", "completed", "x") else " "
        
        content = short_term_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        updated = False
        
        for i, line in enumerate(lines):
            # matches '- [ ] Task' or '- [x] Task'
            if re.match(r"^\s*-\s*\[[ xX]\]\s+", line) and target_text.lower() in line.lower():
                # Replace the checkbox
                lines[i] = re.sub(r"\[[ xX]\]", f"[{checkbox_char}]", line)
                updated = True
                break
        
        if updated:
            short_term_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            
            emit_event(
                event_type="task_updated",
                project_id=project_id,
                actor=ctx.agent_id,
                session_id=ctx.session_id,
                payload={"task": target_text, "status": new_status}
            )
            return ActionResult.ok(f"✅ Task updated to '{new_status}': {target_text}")
        else:
            return ActionResult.fail(f"Task not found matching: {target_text}")

    return ActionResult.fail("Unknown subcommand. Use `ls` or `update <task> <status>`.")


def _extract_all_tasks(path: Path) -> list[tuple[str, str]]:
    tasks = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*-\s*\[([ xX])\]\s+(.*)", line)
        if m:
            tasks.append((m.group(1).lower(), m.group(2).strip()))
    return tasks


def _infer_project_from_cwd() -> str | None:
    import os
    cwd = Path(os.getcwd())
    parts = cwd.parts
    for i, part in enumerate(parts):
        if part in ("projects", "workspace") and i + 1 < len(parts):
            return parts[i + 1]
    return None
