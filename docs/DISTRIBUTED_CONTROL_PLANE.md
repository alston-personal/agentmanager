# Distributed AgentOS Control Plane Transport

## Purpose

`DistributedControlPlane` connects Canonical IR to the existing AgentOS capability/task lease store. `DistributedGatewayService` and the HTTP handler expose those same semantics to remote runtimes without moving coordination logic into the transport layer.

The durable rule remains:

> Canonical IR is the continuity boundary. The Control Plane coordinates ownership. A runtime only executes capabilities it explicitly advertises.

## Wire flow

1. `POST /v1/ir/submit`
   - accepts `canonical_ir`
   - validates schema and digest
   - creates an idempotent Control Plane task
2. `POST /v1/lease`
   - accepts `node_id` and `capabilities`
   - leases the next compatible IR task
   - returns the immutable Canonical IR plus its input digest
3. Runtime executes the IR with a capability-gated `RemoteRuntimeWorker`.
4. `POST /v1/tasks/{task_id}/complete`
   - accepts `runtime_result`
   - verifies `input_ir_id` and `input_digest` against the leased task
   - persists the result and continuation IR
   - optionally enqueues the continuation when `auto_continue` is explicitly enabled
5. `GET /v1/tasks/{task_id}` returns current coordination state.

`GET /health` is intentionally unauthenticated and carries no project data.

## Auto-continuation safety

Auto-continuation is opt-in. `ExecutionOutcome(auto_continue=True)` marks the derived continuation as eligible for automatic submission. The Control Plane enforces a hop limit (default 32), so a cycle between two runtimes cannot continue indefinitely.

The continuation preserves `parent_ir_id`, increments `hop_count`, and cannot change `project_id` during completion validation.

## Network security

The MVP gateway uses bearer-token authentication. Binding to a non-loopback interface without `AGENTOS_CONTROL_PLANE_TOKEN` is rejected at startup.

Example local-only launch:

```bash
python3 scripts/distributed_gateway.py --host 127.0.0.1 --port 8765
```

Example remote-capable launch:

```bash
export AGENTOS_CONTROL_PLANE_TOKEN='replace-with-secret-store-value'
python3 scripts/distributed_gateway.py --host 0.0.0.0 --port 8765
```

Production exposure should still terminate TLS in a hardened reverse proxy or private overlay network. The bearer token is an MVP transport credential, not the long-term node identity design.

## What this unlocks next

The HTTP boundary is sufficient for the next adapters to be thin clients:

- Web Agent Adapter: translate agent state to/from Canonical IR and call submit/task APIs.
- Remote Runtime daemon: long-poll lease, execute registered capabilities, complete task.
- GitHub Actions Adapter: receive/lease an IR through a reachable gateway or a future GitHub-native transport bridge.
- Cross-agent continuation: a completed runtime can enqueue the next capability-specific IR without a human copying the handoff.
