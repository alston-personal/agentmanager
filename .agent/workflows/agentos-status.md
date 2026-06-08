---
description: Render a consolidated AgentOS status report with roles, capabilities, projects, specs, and memory health
---

# /agentos-status - Consolidated AgentOS Status Center

This workflow gives a fast, system-level snapshot of AgentOS:

1. Roles and their memory/skill scope
2. Projects and capability declarations
3. Spec drift and ownership gaps
4. Memory health and growth risk
5. Recommended next improvements

## Execution

```bash
python3 scripts/agentos_status.py
```

Use `--json` for machine-readable output.

