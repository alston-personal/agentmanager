from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except Exception as exc:  # pragma: no cover
    raise SystemExit("PyYAML is required for closure audit") from exc

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = ROOT / ".agent" / "closure" / "ledger.yaml"

ORDER = {
    "DISCOVERED": 0,
    "SPECIFIED": 1,
    "PROTOTYPED": 2,
    "IMPLEMENTED": 3,
    "INTEGRATED": 4,
    "VERIFIED": 5,
    "OPERATING": 6,
    "GUARDED": 7,
    "CLOSED": 8,
}

REQUIRED_FIELDS = (
    "id",
    "owner",
    "stage",
    "implementation",
    "integration_evidence",
    "verification_evidence",
    "operating_evidence",
    "regression_guard",
    "gaps",
)


def load_ledger(path: Path = DEFAULT_LEDGER) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("closure ledger root must be a mapping")
    return data


def _nonempty(value: Any) -> bool:
    return isinstance(value, list) and len(value) > 0


def audit(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()

    for item in data.get("items", []) or []:
        if not isinstance(item, dict):
            errors.append("closure item must be a mapping")
            continue

        missing = [field for field in REQUIRED_FIELDS if field not in item]
        if missing:
            errors.append(f"{item.get('id', '<unknown>')}: missing fields {', '.join(missing)}")
            continue

        item_id = str(item["id"])
        if item_id in seen:
            errors.append(f"{item_id}: duplicate id")
        seen.add(item_id)

        stage = str(item["stage"])
        if stage not in ORDER:
            errors.append(f"{item_id}: unknown stage {stage}")
            continue

        if not str(item.get("owner") or "").strip():
            errors.append(f"{item_id}: owner is required")

        rank = ORDER[stage]
        if rank >= ORDER["IMPLEMENTED"] and not _nonempty(item["implementation"]):
            errors.append(f"{item_id}: {stage} requires implementation evidence")
        if rank >= ORDER["INTEGRATED"] and not _nonempty(item["integration_evidence"]):
            errors.append(f"{item_id}: {stage} requires integration evidence")
        if rank >= ORDER["VERIFIED"] and not _nonempty(item["verification_evidence"]):
            errors.append(f"{item_id}: {stage} requires verification evidence")
        if rank >= ORDER["OPERATING"] and not _nonempty(item["operating_evidence"]):
            errors.append(f"{item_id}: {stage} requires operating evidence")
        if rank >= ORDER["GUARDED"] and not _nonempty(item["regression_guard"]):
            errors.append(f"{item_id}: {stage} requires regression guard")

        if stage == "CLOSED" and item["gaps"]:
            errors.append(f"{item_id}: CLOSED item cannot retain gaps")

    return errors


def render_summary(data: dict[str, Any]) -> str:
    rows = []
    for item in data.get("items", []) or []:
        if not isinstance(item, dict):
            continue
        rows.append(
            (
                str(item.get("id", "?")),
                str(item.get("stage", "?")),
                len(item.get("gaps") or []),
            )
        )
    rows.sort(key=lambda r: (ORDER.get(r[1], -1), r[0]))
    lines = ["Closure Reality", "==============="]
    lines.extend(f"{stage:12} gaps={gaps:<2} {item_id}" for item_id, stage, gaps in rows)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate AgentOS closure ledger")
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()

    data = load_ledger(args.ledger)
    errors = audit(data)
    if args.summary:
        print(render_summary(data))
    if errors:
        print("Closure audit FAILED")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Closure audit PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
