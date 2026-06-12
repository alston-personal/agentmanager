import re
from pathlib import Path
from typing import Dict, Any

from runtime_core.interfaces import ContextProviderInterface, SessionManagerInterface
def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""

class AgentOSContextAdapter(ContextProviderInterface):
    """
    Bridges the ContextProviderInterface to AgentOS's symlink-based memory system.
    Reads and writes SHORT_TERM.md and STATUS.md.
    """
    def __init__(self, project_root: Path, data_root: Path):
        self.project_root = project_root.expanduser().resolve()
        self.data_root = data_root.expanduser().resolve()
        
        project_name = self.project_root.name
        self.project_data_root = self.data_root / "projects" / project_name
        self.short_term_path = self.project_data_root / "memory" / "SHORT_TERM.md"
        self.status_path = self.project_data_root / "STATUS.md"

    def get_short_term_context(self) -> str:
        return _read_text(self.short_term_path)

    def get_status_context(self) -> str:
        return _read_text(self.status_path)

    def update_short_term_context(self, payload: Dict[str, Any]) -> None:
        self.short_term_path.parent.mkdir(parents=True, exist_ok=True)
        content = _read_text(self.short_term_path).rstrip()
        close_section = "\n".join(
            [
                "## Session Close",
                f"- Session ID: `{payload.get('session_id', 'unknown')}`",
                f"- Closed At: {payload.get('ended_at', 'unknown')}",
                f"- Summary: {payload.get('summary', 'unknown')}",
                f"- Branch: `{payload.get('branch', 'unknown')}`",
                f"- Pending Tasks: {len(payload.get('pending_tasks', []))}",
                f"- Blockers: {len(payload.get('blockers', []))}",
                f"- Next Steps: {len(payload.get('next_steps', []))}",
            ]
        )
        if content:
            if "## Session Close" in content:
                prefix, _, remainder = content.partition("## Session Close")
                tail = remainder
                for marker in ("\n## ", "\n# "):
                    idx = tail.find(marker, 1)
                    if idx != -1:
                        tail = tail[idx:]
                        break
                    tail = ""
                new_content = prefix.rstrip() + "\n\n" + close_section
                if tail:
                    new_content += "\n" + tail.lstrip()
            else:
                new_content = content + "\n\n" + close_section + "\n"
        else:
            new_content = "# SHORT_TERM.md\n\n" + close_section + "\n"
        self.short_term_path.write_text(new_content.rstrip() + "\n", encoding="utf-8")

    def update_status_context(self, payload: Dict[str, Any]) -> None:
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        content = _read_text(self.status_path)
        if not content.strip():
            content = "---\n---\n\n# Project Status\n\n## 📍 Summary\n| Metric | Value |\n| :--- | :--- |\n| **Last Status** | N/A |\n| **Last Updated** | N/A |\n\n## 🪵 Activity Log (Latest on Top)\n<!-- LOG_START -->\n"

        summary_value = payload.get("summary", "")
        updated_value = payload.get("ended_at", "").replace(" UTC", "")
        content = re.sub(
            r"(\|\s*\*\*Last Status\*\*\s*\|\s*)([^|]+?)(\s*\|)",
            lambda match: f"{match.group(1)}{summary_value}{match.group(3)}",
            content,
            count=1,
        )
        content = re.sub(
            r"(\|\s*\*\*Last Updated\*\*\s*\|\s*)([^|]+?)(\s*\|)",
            lambda match: f"{match.group(1)}{updated_value}{match.group(3)}",
            content,
            count=1,
        )
        activity_entry = (
            f"- `{updated_value}` 🤝 **SESSION CLOSE**: {summary_value} "
            f"(Session `{payload.get('session_id', 'unknown')}`, branch `{payload.get('branch', 'unknown')}`, "
            f"pending {len(payload.get('pending_tasks', []))}, blockers {len(payload.get('blockers', []))}, next {len(payload.get('next_steps', []))})"
        )
        if "<!-- LOG_START -->" in content:
            content = content.replace("<!-- LOG_START -->", "<!-- LOG_START -->\n" + activity_entry, 1)
        else:
            content = content.rstrip() + "\n\n## 🪵 Activity Log (Latest on Top)\n<!-- LOG_START -->\n" + activity_entry + "\n"

        session_block = "\n".join(
            [
                "",
                "## 🤝 Recent Session Close",
                f"- Session ID: `{payload.get('session_id', 'unknown')}`",
                f"- Summary: {summary_value}",
                f"- Pending Tasks: {len(payload.get('pending_tasks', []))}",
                f"- Blockers: {len(payload.get('blockers', []))}",
                f"- Next Steps: {len(payload.get('next_steps', []))}",
                f"- Branch: `{payload.get('branch', 'unknown')}`",
            ]
        )
        if "## 🤝 Recent Session Close" in content:
            content = re.sub(r"\n## 🤝 Recent Session Close.*", session_block + "\n", content, flags=re.S)
        else:
            content = content.rstrip() + session_block + "\n"
        self.status_path.write_text(content.rstrip() + "\n", encoding="utf-8")


class AgentOSSessionAdapter(SessionManagerInterface):
    """
    Bridges the SessionManagerInterface to AgentOS's existing session_lifecycle.
    """
    def __init__(self, project_root: Path, data_root: Path):
        self.project_root = project_root
        self.data_root = data_root

    def start_session(self) -> str:
        # TODO: Link to actual startup logic
        return "session_id_placeholder"

    def close_session(self, session_id: str, summary: str) -> None:
        from agent_core.session_lifecycle import close_session
        close_session(
            project_root=self.project_root,
            data_root=self.data_root,
            summary=summary
        )
