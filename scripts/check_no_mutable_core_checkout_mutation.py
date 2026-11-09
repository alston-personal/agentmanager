from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(".github/workflows")
MUTABLE = "/home/ubuntu/agentmanager"

# Fetching/reading the source cache is allowed. Mutating its working tree is not.
GIT_WORKTREE_MUTATION = re.compile(
    r"(?:git\s+(?:-C\s+\S+\s+)?(?:pull|merge|reset|checkout|switch|clean)\b)",
    re.IGNORECASE,
)
DIRECT_WRITE = re.compile(
    r"(?:^|[;&|]\s*)(?:cat|cp|mv|rsync|install)\b[^\n]*?(?:>|\s)" +
    re.escape(MUTABLE) + r"(?:/|\b)",
    re.IGNORECASE | re.MULTILINE,
)
REDIRECT_WRITE = re.compile(
    r">>?(?:\s*)"+re.escape(MUTABLE)+r"/",
    re.IGNORECASE,
)

violations: list[str] = []
for path in sorted(ROOT.glob("*.yml")):
    text = path.read_text(encoding="utf-8", errors="replace")
    if MUTABLE not in text:
        continue

    lines = text.splitlines()
    for idx, line in enumerate(lines, start=1):
        if MUTABLE not in line:
            continue
        lower = line.casefold()
        if REDIRECT_WRITE.search(line) or DIRECT_WRITE.search(line):
            violations.append(f"{path}:{idx}:direct_write")
        if GIT_WORKTREE_MUTATION.search(line):
            violations.append(f"{path}:{idx}:git_worktree_mutation")
        # Commands that cd into the mutable checkout and then mutate it may place
        # the git verb later on the same line.
        if ("cd " + MUTABLE) in line and re.search(r"\bgit\s+(pull|merge|reset|checkout|switch|clean)\b", line, re.I):
            violations.append(f"{path}:{idx}:cd_git_worktree_mutation")

if violations:
    print("mutable_core_checkout_guard=FAIL")
    for item in violations:
        print("violation=" + item)
    raise SystemExit(2)

print("mutable_core_checkout_guard=PASS")
