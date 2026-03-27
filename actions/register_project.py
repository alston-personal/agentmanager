"""
actions/register_project.py
Refactored register project action. Now initializes `project.yaml` correctly
instead of just copying `STATUS.md`, properly creating the Agent OS data structure.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from agent_core.context import RuntimeContext
from agent_core.registry import registry, ActionResult
from agent_core.config import CENTRAL_PROJECTS_DIR
from agent_core.models import ProjectRecord, ProjectHealth
from agent_core.project_store import save_project
from agent_memory.event_store import emit as emit_event


@registry.register(
    "register-project",
    description="Register a new project in the agent-data layer",
    aliases=["register", "add-project"],
    requires_project=False,
)
def handle_register(ctx: RuntimeContext) -> ActionResult:
    if not ctx.args:
        return ActionResult.fail("Usage: /register-project <project_slug> [--sector Product|Creative|Infrastructure|Research]")

    slug = ctx.args[0].lower()
    sector = ctx.flags.get("sector", "Product")
    
    if not slug.replace("-", "").isalnum():
        return ActionResult.fail("Invalid project slug. Use only letters, numbers, and hyphens.")

    project_dir = CENTRAL_PROJECTS_DIR / slug
    if project_dir.exists():
        return ActionResult.fail(f"Project directory already exists: {project_dir}")

    # 1. Create directories
    project_dir.mkdir(parents=True)
    (project_dir / "memory").mkdir()
    (project_dir / "sessions").mkdir()

    # 2. Write project.yaml
    now = datetime.now(timezone.utc).isoformat()
    project = ProjectRecord(
        project_id=slug,
        display_name=slug,
        phase="idea",
        status="🆕 Registered",
        health=ProjectHealth(freshness="unknown", sync_state="pending_report", last_verified_at=now),
        sector=sector,
        priority=5,
        created_at=now,
        updated_at=now,
        actual_code_path=f"workspace/{slug}",
        current_focus="Define objectives",
        next_action="Define Project Scope",
    )
    save_project(project)

    # 3. Write default SHORT_TERM.md and LONG_TERM.md
    short_term = project_dir / "memory" / "SHORT_TERM.md"
    short_term.write_text(f"# {slug} Short Term Tasks\n- [ ] Define Project Scope\n", encoding="utf-8")
    
    long_term = project_dir / "memory" / "LONG_TERM.md"
    long_term.write_text(f"# {slug} Long Term Goals\n- TBD\n", encoding="utf-8")
    
    # 4. Write STATUS.md for legacy compatibility
    status_md = project_dir / "STATUS.md"
    status_md.write_text(f"# {slug} Status\n| **Last Status** | 🆕 Registered |\n| **Last Updated** | {now[:10]} |\n- Initial setup.\n", encoding="utf-8")

    # 5. Emit registration event
    emit_event(
        event_type="project_registered",
        project_id=slug,
        actor=ctx.agent_id,
        session_id=ctx.session_id,
        payload={"sector": sector}
    )

    return ActionResult.ok(f"✅ Project `{slug}` registered successfully in Agent Data Layer.\nSector: {sector}")
