"""
actions/snapshot.py
/snapshot action — create a memory snapshot for a project.
Thin wrapper around scripts/create_snapshot.py, with proper event emission.
"""
from __future__ import annotations

from agent_core.context import RuntimeContext
from agent_core.registry import registry, ActionResult
from agent_memory.event_store import emit as emit_event


@registry.register(
    "snapshot",
    description="Create a memory snapshot for a project",
)
def handle_snapshot(ctx: RuntimeContext) -> ActionResult:
    import subprocess
    import sys
    from agent_core.config import SCRIPTS_DIR

    script = SCRIPTS_DIR / "create_snapshot.py"
    if not script.exists():
        return ActionResult.fail(f"create_snapshot.py not found at {script}")

    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
    )

    success = result.returncode == 0
    output = (result.stdout or result.stderr or "").strip()

    if success:
        emit_event(
            event_type="snapshot_created",
            project_id=ctx.project_id or "system",
            actor=ctx.agent_id,
            session_id=ctx.session_id,
        )

    return ActionResult(
        success=success,
        output=f"{'✅ Snapshot created' if success else '❌ Snapshot failed'}\n{output}",
        exit_code=result.returncode,
    )
