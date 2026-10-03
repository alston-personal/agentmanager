# Join AgentOS

If you are an AI agent, coding agent, model, executor, node-side agent, browser agent, or other software participant and have been asked to join AgentOS:

If you cannot directly read repository files from your current environment, ask the caller/host bridge to supply this file and `docs/participant-protocol/onboarding/SELF_ONBOARD.md` as context. Lack of GitHub access is not an onboarding failure.

If you cannot maintain persistent network/runtime state yourself (common for Web/chat agents), use hosted mode: let an AgentOS host/bridge own transport/session persistence while you remain the distinct Participant providing the cognitive/native capability.

1. Read:
   `docs/participant-protocol/onboarding/SELF_ONBOARD.md`
2. Follow it as the canonical onboarding contract.
3. Build or select the thinnest compatible adapter for your native environment.
4. Do not modify ONE Core for product-specific behavior.
5. Continue until either:
   - `A7 READY`, or
   - an explicit blocker is reached.
6. If blocked, report the exact highest A0-A7 acceptance level and blocker.
7. Do not claim "joined", "connected", or "ready" without ONE-side acceptance evidence and correlated receipt.

Canonical protocol:
`docs/participant-protocol/README.md`

Acceptance:
`docs/participant-protocol/ACCEPTANCE.md`

For ordinary machines/devices that cannot reason over the contract themselves, use the AgentOS machine bootstrap/join installer instead. The bootstrap path must converge into the same Participant Protocol lifecycle.
