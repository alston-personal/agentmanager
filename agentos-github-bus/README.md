# AgentOS GitHub Command Bus

This directory is the account-scoped fallback transport from ChatGPT's official GitHub connector to ONE.

## Request

Create one immutable JSON file under `requests/`:

```json
{
  "protocol": "agentos.github-command/v1",
  "request_id": "chatgpt-<unique-id>",
  "action": "resume",
  "hint": "",
  "principal": "chatgpt-github"
}
```

Supported read-only actions:

- `resume`: resolve the authoritative active project from ONE, then resume it.
- `project_state`: read one explicit project state; requires `project_id`.

The GitHub Actions workflow processes the request on the ONE host and writes one response under `responses/<request_id>.json`.

## Response

```json
{
  "protocol": "agentos.github-command-response/v1",
  "request_id": "...",
  "ok": true,
  "action": "resume",
  "project_id": "...",
  "result": {"...": "ONE canonical response"}
}
```

The GitHub repository is transport only. Canonical state remains in ONE. Device, browser and ChatGPT conversation identifiers must never become durable AgentOS identity.
