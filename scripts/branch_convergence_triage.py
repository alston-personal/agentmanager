"""Mechanically classify branch-diff paths without claiming feature equivalence."""
import json
import sys
from collections import Counter
from pathlib import Path

def domain(p):
    for prefix, label in (
        (".agent/", "governance"), (".agentos/", "governance"),
        (".github/workflows/", "ci-workflows"), ("agent_core/", "core"),
        ("runtime_core/", "core"), ("dashboard/", "dashboard"),
        ("scripts/", "scripts"), ("tests/", "tests"),
    ):
        if p.startswith(prefix):
            return label
    return "other"

def transform(records):
    out = []
    for record in records:
        code = record["status"][:1]
        direction = {"A": "INTEGRATION_ONLY_PATH", "D": "MAIN_ONLY_PATH",
                     "M": "DIFFERENT_ON_BOTH"}.get(code, "UNKNOWN_DIRECTION")
        out.append({**record, "path_direction": direction, "domain": domain(record["path"]),
                    "classification": "UNKNOWN", "evidence_level": "path-only",
                    "next_action": "review patch equivalence, owner, consumers and release contract"})
    return out

if __name__ == "__main__":
    source = Path(sys.argv[1])
    dest = Path(sys.argv[2])
    rows = transform(json.loads(source.read_text())["files"])
    summary = dict(sorted(Counter((x["domain"], x["path_direction"]) for x in rows).items()))
    dest.write_text(json.dumps({"schema": "agentos.branch-triage/v1", "records": rows,
        "summary": [{"domain": d, "direction": side, "count": n}
                    for (d, side), n in summary.items()]}, indent=2, ensure_ascii=False))
    print(f"triage_records={len(rows)}")
