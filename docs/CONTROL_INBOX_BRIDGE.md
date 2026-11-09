# Control Inbox → ONE Bridge

Status: Core #182 static hardening candidate. This document describes the source-controlled bridge/runtime contract; it does **not** claim that the hardened unit is already installed or running on Oracle.

## Purpose

For ChatGPT plans/surfaces that do not yet expose a native authorized ONE write transport, the bootstrap path remains:

```text
ChatGPT Web -> GitHub Issue #50 mailbox -> Control Inbox bridge -> ONE ControllerService -> Node
```

GitHub is only the temporary mailbox. ONE remains the control-plane authority. GitHub Actions is not a fallback carrier for AgentOS control-plane intents.

## Source of truth

- bridge: `agent_core/control_inbox_bridge.py`
- regressions: `tests/test_control_inbox_bridge.py`
- service template: `.agent/scripts/agentos-control-inbox-bridge.service`
- non-secret environment example: `config/control-inbox.env.example`

## Security contract

The bridge accepts only `agentos.control-command/v0.1` JSON comments from the configured login, for the configured repository/issue, before command expiry, and only when `action` is present in the mandatory local `AGENTOS_CONTROL_ALLOWED_ACTIONS` set.

The local allowlist is an additional fence, not a replacement for ONE authorization. Generic shell, filesystem and input action prefixes are rejected even if accidentally configured. The bridge does not provide arbitrary executable/argv authority.

Commands have a maximum lifetime of 600 seconds and a small positive clock-skew allowance. Expired commands never dispatch.

## Delivery/idempotency contract

A deterministic ONE task id is derived from `command_id`. The bridge persists a command claim **before** dispatch. If the process dies after claim but before a terminal result, restart must not blindly redispatch the privileged operation; the result becomes `unknown` / `bridge_interrupted_after_claim` until independently verified.

Terminal results are persisted before GitHub publication. Unposted terminal results are retried on later cycles. This gives at-least-once result publication without pretending privileged side effects are known after an interrupted claim.

## ONE protocol handling

A dispatch succeeds only for HTTP 2xx plus a structured object with `ok: true`. The bridge does not hard-code HTTP 202. HTTP error bodies are not copied into exceptions/results. Transport/protocol failures use bounded stable classifications such as `one_unavailable`, `one_dispatch_http_500`, or `one_dispatch_protocol_error`.

## Receipt privacy boundary

GitHub results are evidence, not a debug dump. Receipts are projected to bounded action-specific fields. In particular, the public mailbox must not receive local usernames, executable/private paths, window titles, bearer tokens, raw vendor/session payloads, or arbitrary backend error bodies.

## Runtime environment

Populate a host-local environment file based on `config/control-inbox.env.example`; the source-controlled example intentionally contains no secrets. The service template expects `/home/ubuntu/.config/agentos/control-inbox.env` and runs the module from `/home/ubuntu/agentmanager`.

Required secrets:
- `AGENTOS_GITHUB_TOKEN` (or `GH_TOKEN`)
- `AGENTOS_CONTROLLER_TOKEN`

Required authority fence:
- `AGENTOS_CONTROL_ALLOWED_ACTIONS`

The durable bridge state defaults under `/home/ubuntu/agent-data/runtime/control-inbox/state.json` and must be writable by the service identity. The populated environment file should be mode 0600 and must never be committed.

## Deployment boundary

Merging the static source/service contract to `core/integration` does not install, enable, restart, or mutate the Oracle runtime. Deployment requires an independently authorized bounded runtime path and a post-deploy probe. Do not use GitHub Actions as a generic control-plane substitute to install this service.

Issue #50 is a machine mailbox, not an engineering discussion thread. Source/CI work for #182 must not post probe or status comments there unless an explicitly authorized live acceptance requires it.

## Verification

The hosted guard runs `tests.test_control_inbox_bridge` without Oracle/self-hosted runners. Static tests cover author/schema/expiry fencing, duplicate command handling, interrupted-claim UNKNOWN semantics, 2xx protocol handling, safe HTTP failures, privacy projection, unexpected-error redaction, and generic-action rejection.

Live acceptance is separate: after governed deployment, a fresh authorized control command must traverse the mailbox → hardened bridge → ONE and return a sanitized receipt, with no GitHub Actions control-plane fallback.
