# ChatGPT Web Node

## Goal

Treat ChatGPT Web as a replaceable AgentOS executor instead of relying on ChatGPT conversation memory for operational continuity.

A conversation rollover must not be a persistence boundary. Given the same AgentOS project, a new ChatGPT conversation should be able to attach and recover the authoritative goal, constraints, current IR, compiled execution context, latest task and recommended continuation action.

## Current implementation

`agentos_node/chatgpt_web_node.py` implements the transport-neutral bootstrap contract:

1. call the existing authenticated `POST /v1/attach` Control Plane operation;
2. bind the returned `session_id`, project state and compiled execution context;
3. validate the current Canonical IR belongs to the attached project;
4. build an immutable `WebAgentAdapter` request with `input_ir_id` and digest binding;
5. return `agentos.chatgpt-web-bootstrap/v1` for transport by a browser bridge, extension, connector or future native integration.

CLI:

```bash
export AGENTOS_CONTROL_PLANE_URL=https://studio.milkcat.org/dashboard/api/agentos
export AGENTOS_CONTROL_PLANE_TOKEN='...scoped client token...'
python3 scripts/chatgpt_web_node.py <project-id>
```

The CLI never needs browser credentials and the model is never allowed to construct trusted continuation lineage.

## Trust boundary

ChatGPT Web is not the state owner.

```text
ChatGPT conversation
    |
    | semantic output only
    v
browser/connector transport
    |
    v
ChatGPTWebBootstrap + WebAgentAdapter
    |
    v
Control Plane / State Kernel
```

The Control Plane remains authoritative for canonical state. The web model may reason over the attached context, but project identity, IR lineage, digest binding, task completion and receipts stay outside the model boundary.

## Continuity Floor acceptance test

The first real regression target is the existing 3D Layout work:

1. Chat A is attached to the 3D Layout AgentOS project and performs work against the existing `layoutlib` + demo implementation.
2. The current canonical state records the real repo/workspace state and next action.
3. Chat A is abandoned or reaches its conversation limit.
4. Chat B starts with no useful ChatGPT-native conversation history.
5. Chat B attaches to the same AgentOS project.
6. The bootstrap packet must recover the actual implementation state, not merely the semantic topic "3D Layout".
7. Chat B must identify the existing `layoutlib`, demo, last verified action and next action without redesigning the project from scratch.

Failure mode to prevent:

```text
"continue 3D Layout"
  -> semantic memory only
  -> generic 2D-to-3D architecture proposal
```

Required behavior:

```text
"continue 3D Layout"
  -> AgentOS attach
  -> canonical project state
  -> compiled execution context
  -> exact next implementation action
```

## Remaining work

The bootstrap/resume core is intentionally transport-neutral. To make the ChatGPT website itself behave as a zero-manual-step node, one authorized transport must still carry the bootstrap packet into a new ChatGPT conversation and return the constrained web-agent response. Candidate transports remain a browser extension, local browser relay, an authorized connector, or a future native ChatGPT integration.

That transport must not become a second state store. It should only move AgentOS envelopes and preserve the existing digest/session binding.
