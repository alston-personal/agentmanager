"""Fail-closed path/effect authorization for AgentOS node workspaces.

OS permissions only define what a service account *can* do. This guard defines
what AgentOS authorizes it to do inside a declared node workspace contract.
"""

from __future__ import annotations

from dataclasses import dataclass
import fnmatch
import json
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class WorkspaceDecision:
    allowed: bool
    path: str
    effect: str
    reason: str
    matched_role: str | None = None


class WorkspaceGuard:
    def __init__(self, contract: dict[str, Any]) -> None:
        if contract.get("schema") != "agentos.node-workspace-contract/v1":
            raise ValueError("unsupported workspace contract schema")
        self.contract = contract

    @classmethod
    def from_file(cls, path: str | Path) -> "WorkspaceGuard":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("workspace contract root must be an object")
        return cls(payload)

    @staticmethod
    def _inside(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    @staticmethod
    def _matches_any(relpath: str, patterns: Iterable[str]) -> bool:
        relpath = relpath.replace("\\", "/").lstrip("/")
        return any(fnmatch.fnmatch(relpath, pattern) for pattern in patterns)

    def evaluate(self, path: str | Path, effect: str) -> WorkspaceDecision:
        requested = Path(path).expanduser().resolve(strict=False)
        effect = str(effect or "").strip()
        if not effect:
            return WorkspaceDecision(False, str(requested), effect, "effect is required")

        matches: list[tuple[int, dict[str, Any], Path]] = []
        for entry in self.contract.get("paths", []):
            if not isinstance(entry, dict) or not entry.get("path"):
                continue
            root = Path(str(entry["path"])).expanduser().resolve(strict=False)
            if requested == root or self._inside(requested, root):
                matches.append((len(root.parts), entry, root))
        if not matches:
            return WorkspaceDecision(False, str(requested), effect, "path is outside declared workspace contract")

        _, entry, root = max(matches, key=lambda item: item[0])
        role = str(entry.get("role") or "") or None
        allowed_effects = {str(item) for item in entry.get("allowed_effects", [])}
        forbidden_effects = {str(item) for item in entry.get("forbidden_effects", [])}
        if effect in forbidden_effects:
            return WorkspaceDecision(False, str(requested), effect, "effect explicitly forbidden", role)
        if effect not in allowed_effects:
            return WorkspaceDecision(False, str(requested), effect, "effect not explicitly allowed", role)

        relpath = "" if requested == root else requested.relative_to(root).as_posix()
        protected = [str(item) for item in entry.get("protected_patterns", [])]
        if protected and self._matches_any(relpath, protected):
            return WorkspaceDecision(False, str(requested), effect, "path matches protected pattern", role)

        allowed = [str(item) for item in entry.get("allowed_write_patterns", [])]
        if effect in {"write", "create", "delete", "commit"} and allowed:
            if not self._matches_any(relpath, allowed):
                return WorkspaceDecision(False, str(requested), effect, "write path not allowlisted", role)

        return WorkspaceDecision(True, str(requested), effect, "authorized by workspace contract", role)
