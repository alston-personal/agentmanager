# AgentOS — Startup Profile Source of Truth

Status: draft for Claude for Startups review, 2026-10-08. Product claims are **not** a claim of incorporation, funding, or general production readiness.

## Identity
- Project: AgentOS
- Builder: independent, self-funded solo developer (not incorporated)
- Domain controlled by founder: milkcat.org
- Intended public product profile: planned at studio.milkcat.org/agentos/; **not deployed or verified**
- Related application showcase: Milkcat World /world/ (experimental 3D experience)

## Product thesis
**Persistent Intelligence. Durable Capabilities. Measurable Growth.**
AgentOS is an experimental control plane and runtime for AI-agent work across sessions, models, nodes, and tools. It moves task continuity, capability governance, and execution evidence outside the model conversation.

## Evidence tiers and wording
| Topic | Evidence | Safe public statement |
| --- | --- | --- |
| Continuation state / persistent task records | README; docs/CURRENT_STATE.md; agent_core/control_plane.py; tests/test_control_plane.py | Implemented and tested building blocks |
| Session handoff | agent_core/session_lifecycle.py; tests/test_session_close.py | Implemented and tested |
| Node capability and governance discovery | agent_core/node_registry.py; scripts/agentos_node.py; tests | Implemented and tested foundations |
| Governed execution/receipts | docs/CURRENT_STATE.md; agent_core/controller_service.py; historical live evidence | Components implemented; integration still being validated |
| Work completion ownership | scripts/work_completion.py; tests; docs/CURRENT_STATE.md | Implemented and live-accepted slice, not general autonomous completion |
| Durable capability invariant | agentmanager PR #1675 (open, unmerged as checked 2026-10-08) | In development; contract tests do not equal full runtime acceptance |
| Persistent Supervisor | issue #200; live acceptance pending | In development, not autonomous general availability |
| Cognitive IR / cross-model sufficiency | docs/CURRENT_STATE.md | Research, not generally proven |
| Measurable self-growth | AgentOS Growth Proof objective | Research goal; benchmark still required |
| 3D world | https://studio.milkcat.org/world/ | Separate experimental showcase; not a prerequisite to understand AgentOS |

## Primary application narrative
We are building AgentOS to address the fragility of agent tasks that depend on one chat session or model retaining context. The platform explores durable task state, reusable capability contracts, governed execution across heterogeneous nodes, and receipt-based verification. Our next research goal is evidence-backed self-improvement, measured under controlled model/provider and task conditions.

## Claude for Startups intended use
- Evaluate Claude API / Claude Code as replaceable inference and execution providers in a multi-model agent runtime.
- Benchmark reliability, intervention rates, recovery, and repeatability with fixed test tasks and budgets.
- Use a separate spending cap and audit trail for granted credits.
- Verify eligibility truthfully as an unincorporated independent project; do not claim startup program approval.

## Publication rules
Website must clearly label **Implemented & Tested**, **In Active Development**, and **Research Goals**. No unverified user counts, revenue, investment, production availability, benchmarks or company status. Do not put private infrastructure paths, node IDs, secrets or login credentials on the public page.

## Sources checked
- https://github.com/alston-personal/agentmanager/blob/main/README.md
- https://github.com/alston-personal/agentmanager/blob/main/docs/CURRENT_STATE.md (status date 2026-10-02)
- https://github.com/alston-personal/agentmanager/pull/1675 (unmerged as checked 2026-10-08)
- https://github.com/alston-personal/agentmanager/issues/200
