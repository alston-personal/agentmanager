from __future__ import annotations

import re
from pathlib import Path

# One-shot governance codemod; safe to rerun idempotently.

BASELINE = Path(".agentos/governance/legacy-direct-oracle-workflows.txt")
TOP_LEVEL_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*\s*:")


def workflow_dispatch_block(block: list[str]) -> list[str]:
    for i, line in enumerate(block):
        if re.match(r"^  workflow_dispatch\s*:", line):
            end = len(block)
            for j in range(i + 1, len(block)):
                line2 = block[j]
                if re.match(r"^  [A-Za-z_][A-Za-z0-9_-]*\s*:", line2):
                    end = j
                    break
            return block[i:end]
    return ["  workflow_dispatch:\n"]


def quarantine(path: Path) -> bool:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    start = None
    for i, line in enumerate(lines):
        if re.match(r"^on\s*:", line):
            start = i
            break
    if start is None:
        raise RuntimeError(f"workflow missing top-level on: {path}")

    # Inline forms such as "on: [push, workflow_dispatch]" occupy one line.
    inline = lines[start].split(":", 1)[1].strip()
    if inline:
        end = start + 1
        dispatch = ["  workflow_dispatch:\n"]
    else:
        end = len(lines)
        for j in range(start + 1, len(lines)):
            line = lines[j]
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if line[0].isspace():
                continue
            if TOP_LEVEL_KEY.match(line):
                end = j
                break
        dispatch = workflow_dispatch_block(lines[start + 1:end])

    replacement = ["on:\n", *dispatch]
    new_lines = lines[:start] + replacement + lines[end:]
    new_text = "".join(new_lines)
    old_text = "".join(lines)
    if new_text == old_text:
        return False
    path.write_text(new_text, encoding="utf-8")
    return True


def main() -> int:
    targets = [
        Path(line.strip())
        for line in BASELINE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    changed = []
    missing = []
    for path in targets:
        if not path.is_file():
            missing.append(str(path))
            continue
        if quarantine(path):
            changed.append(str(path))

    print(f"legacy_direct_oracle_targets={len(targets)}")
    print(f"legacy_direct_oracle_changed={len(changed)}")
    print(f"legacy_direct_oracle_missing={len(missing)}")
    for item in changed:
        print("quarantined=" + item)
    for item in missing:
        print("missing=" + item)

    # Missing files are acceptable only when legacy debt was already retired.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
