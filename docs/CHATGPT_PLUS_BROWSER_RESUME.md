# ChatGPT Plus Browser Resume

## Purpose

Provide a continuity path for ChatGPT Plus when custom Developer-Mode MCP is not available to the account.

This path reuses the existing external `ai-browser-bridge`; AgentOS does not own ChatGPT DOM selectors, cookies, browser profiles, or login persistence.

## Flow

```text
AgentOS Control Plane
  -> POST /v1/attach
  -> ChatGPTWebBootstrap
  -> compile_resume_prompt()
  -> ai-browser-bridge `bridge ask --provider chatgpt --json ...`
  -> ChatGPT Web
  -> untrusted semantic reply
```

Canonical project state remains authoritative. The browser bridge is transport only.

## Command

On the machine that already has a working, signed-in ChatGPT `ai-browser-bridge` profile:

```bash
export AGENTOS_CONTROL_PLANE_URL='https://<agentos-control-plane>'
export AGENTOS_CONTROL_PLANE_TOKEN='<scoped-token>'
python3 scripts/chatgpt_browser_resume.py <project-id> --intent '繼續'
```

The command first attaches to AgentOS. Only after the authoritative state is restored does it call ChatGPT.

## 3D Layout Continuity Floor

The first real acceptance case is the existing 3D Layout project.

The canonical AgentOS state must contain enough operational information to distinguish the real implementation from a generic topic summary, including as applicable:

- existing `layoutlib` component/repository location;
- demo URL/deployment identity;
- active branch/HEAD or workspace revision;
- last verified action/result;
- current bug or incomplete behavior;
- exact next implementation action.

A fresh ChatGPT conversation receiving the compiled resume prompt must continue from those facts. A generic architecture proposal for 2D-to-3D reconstruction is a regression failure.

## What this does not solve yet

This command can open/use ChatGPT through the external bridge, but it does not intercept a user manually typing `繼續` into an arbitrary already-open ChatGPT tab.

That last UX gap requires one of:

1. native ChatGPT MCP/app support for the account;
2. a browser-side intent interceptor that calls AgentOS before the message is submitted;
3. a ChatGPT-facing authorized integration that can enforce the continuation protocol.

Do not solve this by moving canonical state into the extension or browser profile. Any interceptor must remain a stateless transport and must fail closed when AgentOS resume cannot be obtained.
