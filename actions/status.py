"""
actions/status.py
/status action — show all projects from structured YAML source.

Registered as:  @registry.register("status")
No more regex parsing of STATUS.md markdown.
Falls back gracefully if project.yaml not yet generated.
"""
from __future__ import annotations

from agent_core.context import RuntimeContext
from agent_core.registry import registry, ActionResult
from agent_core.renderer import render_project_table


@registry.register(
    "status",
    description="Show structured status of all projects from project.yaml",
    aliases=["s"],
)
def handle_status(ctx: RuntimeContext) -> ActionResult:
    """
    Primary source: project.yaml (structured YAML, no regex)
    Fallback: STATUS.md regex parsing (legacy, warns user to upgrade)
    """
    try:
        import yaml
        from agent_core.project_store import list_projects

        projects = list_projects()

        if not projects:
            return ActionResult.fail(
                "No `project.yaml` files found.\n"
                "Run: `python3 scripts/init_project_yaml.py` to generate them.",
                exit_code=2,
            )

        # Filter by sector if requested
        sector_filter = ctx.flags.get("sector")
        if sector_filter:
            projects = [p for p in projects if p.sector.lower() == sector_filter.lower()]

        # Sort: priority desc, then name
        projects.sort(key=lambda p: (-p.priority, p.project_id))

        table = render_project_table(projects)

        summary_line = (
            f"_{len(projects)} project(s)"
            + (f" in `{sector_filter}` sector" if sector_filter else "")
            + " — source: `project.yaml`_"
        )

        output = f"## 🗂️ Agent OS Project Status\n\n{table}\n\n{summary_line}"

        return ActionResult.ok(output, data={"project_count": len(projects)})

    except ImportError:
        return _fallback_status()
    except Exception as e:
        return _fallback_status(error=str(e))


def _fallback_status(error: str = "") -> ActionResult:
    """Legacy fallback: regex parse STATUS.md files."""
    import os
    import re
    from glob import glob
    from agent_core.config import CENTRAL_PROJECTS_DIR

    warnings = []
    if error:
        warnings.append(f"project.yaml read failed ({error}), falling back to STATUS.md regex")
    else:
        warnings.append("project.yaml not found — falling back to STATUS.md regex. Run `init_project_yaml.py` to upgrade.")

    status_paths = sorted(glob(str(CENTRAL_PROJECTS_DIR / "*" / "STATUS.md")))
    if not status_paths:
        return ActionResult.fail(
            f"No STATUS.md files found in {CENTRAL_PROJECTS_DIR}",
            exit_code=2,
        )

    def _extract(content: str, label: str) -> str:
        m = re.search(rf"\|\s*\*\*{re.escape(label)}\*\*\s*\|\s*([^|]+?)\s*\|", content)
        return m.group(1).strip() if m else "N/A"

    rows = []
    for path in status_paths:
        name = os.path.basename(os.path.dirname(path))
        content = open(path, encoding="utf-8").read()
        rows.append(
            f"| {name} | {_extract(content, 'Last Status')} "
            f"| {_extract(content, 'Last Updated')} |"
        )

    output = "\n".join([
        "| Project | Status | Updated |",
        "| :--- | :--- | :--- |",
        *rows,
        "",
        "_Source: `STATUS.md` (legacy regex — run `init_project_yaml.py` to upgrade)_",
    ])

    return ActionResult(success=True, output=output, exit_code=0, warnings=warnings)
