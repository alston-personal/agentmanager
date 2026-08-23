"""Load and validate task-neutral master execution exemplars."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class MasterExemplar:
    exemplar_id: str
    observation: str
    decision: str
    action: str
    expected_disposition: str


ALLOWED_DISPOSITIONS = {
    "CONTINUE",
    "CONTINUE_OR_WAIT_FOR_DEPENDENCY",
    "REQUEST_AUTHORITY",
    "INTERRUPTED_BY_USER",
}


def load_master_exemplars(path: str | Path) -> tuple[MasterExemplar, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema") != "agentos.master-trace-exemplars/v1":
        raise ValueError("unsupported master exemplar schema")
    raw = payload.get("exemplars")
    if not isinstance(raw, list) or not raw:
        raise ValueError("master exemplar pack must contain exemplars")

    seen: set[str] = set()
    out: list[MasterExemplar] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("master exemplar must be an object")
        exemplar_id = str(item.get("id") or "")
        if not exemplar_id or exemplar_id in seen:
            raise ValueError("master exemplar ids must be unique and non-empty")
        disposition = str(item.get("expected_disposition") or "")
        if disposition not in ALLOWED_DISPOSITIONS:
            raise ValueError(f"unsupported exemplar disposition: {disposition}")
        fields = [str(item.get(name) or "") for name in ("observation", "decision", "action")]
        if any(not value.strip() for value in fields):
            raise ValueError(f"master exemplar {exemplar_id} is incomplete")
        seen.add(exemplar_id)
        out.append(MasterExemplar(exemplar_id, fields[0], fields[1], fields[2], disposition))
    return tuple(out)


def render_master_bootstrap(exemplars: Iterable[MasterExemplar]) -> str:
    """Render concise behavioral demonstrations without task-specific answers."""
    blocks = [
        "Execution regime: answerability is not completion. "
        "After every receipt, reassess the parent goal and continue while a material, authorized, derivable closure gap remains."
    ]
    for exemplar in exemplars:
        blocks.append(
            f"[{exemplar.exemplar_id}] Observation: {exemplar.observation} "
            f"Decision: {exemplar.decision} Action: {exemplar.action} "
            f"Disposition: {exemplar.expected_disposition}."
        )
    return "\n".join(blocks)
