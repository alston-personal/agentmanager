# AgentOS Employee roster v1 (Core #420)

This is an **operator-local, read-only canonical Employee identity / assignment evidence projection**, not a scheduler, route, provider selector, health attestation, public dashboard, or proof that a product Employee is currently autonomously working.

Run on the authorized host where the already-existing Employee Runtime root is available:

    python3 -m agent_core.employee_roster --runtime-root /absolute/existing/employee-runtime

The root must be a known existing canonical Employee runtime directory; the command does not initialize it, write state, deploy anything, invoke an executor, or read employee private memories. Do not expose the output at a public endpoint. A server-backed view requires AgentOS/Milkcat authentication and separate operator authorization.

The projection inventories on-disk Employee records plus the fixed initial known contracts for Spec Steward, Zeus Writer, and YouTube AI Manager. Missing contracts are explicitly \`not_registered\` rather than silently omitted. **Mio is not yet assumed to have a Core Employee ID**: her Persona/social/Telegram runtime must be reconciled to a canonical Employee contract before adding an exact identity to this fixed list. For an unregistered role, do not infer an ID from the public persona name or a chat status file.

The per-assignment states are deliberately conservative:

- \`pending\`: durable assignment exists and has not been claimed; no wake or executor success implied.
- \`running\`: durable assignment has an unexpired lifecycle lease only. The Worker Host, Node, provider, task effect, and future progress have **not** been verified.
- \`completed | cancelled | blocked | handoff\`: durable terminal state **and** matching canonical terminal lifecycle receipt. This is historical assignment evidence, not current Employee liveness.
- \`unknown\`: expired/missing/mismatched lease, malformed evidence, or a terminal assignment without matching terminal receipt. Never blindly retry unknown external effects.
- \`idle\`: historical terminal assignments and no nonterminal assignment; **not** a claim of autonomous recurrence or health.

\`next_due_at=null\`, \`schedule_verified=false\`, \`executor_available=null\`, \`role_health_verified=false\`, and \`autonomous_liveness_verified=false\` are intentional. Future milestones in #420 must join independently verified schedule, Supervisor/Worker Host, ONE, Node/capability, budget and product-specific receipts before showing a green operational health state. A declared/advertised capability or a recent GitHub PR does not substitute for a live success receipt.

Output excludes assignment goal, raw result summary, private memory, session/model identity, arbitrary file paths and private messages. The logical receipt reference is a lookup key, not authority or a public URL. This CLI is not exposed as a new generic remote execution capability.

Source: \`agent_core/employee_roster.py\`; tests: \`tests/test_employee_roster.py\`. This PR should target \`core/integration\`, preserve all existing protected-main and governed release constraints, and should not be merged or deployed as if #200/#197/#238 live acceptance were already complete.
