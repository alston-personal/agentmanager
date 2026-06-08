---
description: Review specs for ownership, drift, and implementation closure
---

# /spec-steward - Spec Governance Report

This workflow belongs to AgentOS governance. It verifies that specs are not drifting away from implementation.

## What it checks

1. Specs in `/home/ubuntu/agent-data/specs/`
2. Ownership, target projects, and required capabilities
3. Open checklist items and stale specs
4. Capability alignment against `project.yaml` declarations

## Execution

Run the spec stewardship report:

```bash
python3 scripts/spec_steward.py
```

## Expected outcome

- A markdown report is produced in `agent-data/journals/spec_governance/`
- Specs with missing ownership or missing providers are surfaced
- Stale specs are flagged before they silently stall

