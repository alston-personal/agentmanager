from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(".github/workflows")
BASELINE = Path(".agentos/governance/legacy-direct-oracle-workflows.txt")
BREAK_GLASS = {
    ".github/workflows/oracle-one-break-glass-repair.yml",
    ".github/workflows/oracle-runner-recovery.yml",
}

pattern = re.compile(
    r"runs-on:\s*\[(?=[^\]]*self-hosted)(?=[^\]]*oracle)[^\]]*\]",
    re.IGNORECASE,
)

legacy = {
    line.strip()
    for line in BASELINE.read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.lstrip().startswith("#")
}
current = {
    str(path)
    for path in sorted(ROOT.glob("*.yml"))
    if pattern.search(path.read_text(encoding="utf-8", errors="replace"))
}
new_direct = sorted(current - legacy - BREAK_GLASS)
retired = sorted(legacy - current)

print(f"direct_oracle_legacy_current={len(current & legacy)}")
print(f"direct_oracle_legacy_retired={len(retired)}")
print(f"direct_oracle_break_glass={len(current & BREAK_GLASS)}")
if new_direct:
    print("direct_oracle_self_hosted_guard=FAIL")
    for item in new_direct:
        print("new_violation=" + item)
    raise SystemExit(2)

print("direct_oracle_self_hosted_guard=PASS")
