# AgentOS Node Control Protocol (ANCP) v0.1

ANCP is the AgentOS control-plane protocol between a Control Plane and Node
Agents. Agent-to-agent collaboration uses A2A, tool/data access uses MCP, and
internal work delivery may use NATS/JetStream. ANCP carries node lifecycle,
module distribution, task leases, and execution status.

## Transport and envelope

The MVP transport is HTTPS with JSON. A later adapter may use NATS subjects, but
the message shape remains the same.

    {
      "protocol": "ancp",
      "version": "0.1",
      "messageType": "task.submit",
      "messageId": "msg_01...",
      "taskId": "task_01...",
      "correlationId": "workflow_01...",
      "idempotencyKey": "project/env/request-hash",
      "source": {"type": "control-plane", "id": "cp-main"},
      "target": {"nodeId": "node-gpu-01", "capability": "ai.generate"},
      "occurredAt": "2026-07-24T00:00:00Z",
      "deadline": "2026-07-24T00:05:00Z",
      "payload": {}
    }

messageId, taskId, and idempotencyKey are required. Receivers must safely
deduplicate a repeated idempotency key and must not log secret values.

## v0.1 message types

| Direction | Message | Purpose |
|---|---|---|
| Node to Control Plane | node.register | identity, manifest, capabilities |
| Node to Control Plane | node.heartbeat | liveness, resource snapshot, active leases |
| Control Plane to Node | module.install | fetch and verify an immutable artifact |
| Control Plane to Node | module.rollback | switch to a previous verified version |
| Control Plane to Node | task.submit | assign a capability invocation |
| Node to Control Plane | task.lease | accept task with lease expiry |
| Node to Control Plane | task.progress | report stage, percent, and artifacts |
| Control Plane to Node | task.cancel | request cooperative cancellation |
| Node to Control Plane | task.result | success or structured failure |

## Task lifecycle

submitted -> leased -> running -> succeeded|failed|cancelled|expired

Leases have an expiry and heartbeat extension. A task may be retried only when
its module declares the operation idempotent or the request includes a stable
idempotency key. Results should return artifact references, not large binary
payloads inside the control message.

## Security baseline

- mTLS for Node Agent to Control Plane in production
- short-lived node identity token for bootstrap and rotation
- capability and project authorization checked at task submission and execution
- module artifact SHA-256 verification before activation
- explicit secret references, never raw keys in manifests, tasks, or logs
- append-only audit record for registration, install, task, and rollback

## Master Failover & Dynamic Gateway Routing

To prevent paradoxes when swapping `AGENT_MODE=CORE` and `AGENT_MODE=CLIENT` roles across physical machines:

1. **Virtual Gateway Endpoint**: Node gateway URLs (`https://agentos-core.milkcat.org`) must bind to a virtual endpoint (e.g. Cloudflare Tunnel / DDNS / Virtual IP), not a static physical hostname. Swapping CORE host requires updating the tunnel/DNS target to the active CORE host.
2. **CLIENT Rejection & Discovery Fallback**: If a Node connects to a host operating in `CLIENT` mode, the host MUST reject registration with `409 Conflict (CLIENT_MODE_REJECT)`. The Node MUST fall back to secondary gateways or local standalone degraded mode.
3. **Secondary Gateway Resolution**: Node configuration (`~/.agentos/config.json`) supports ordered `secondary_gateways` for automated failover during Control Plane migration.

