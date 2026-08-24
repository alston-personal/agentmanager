# Linux Browser Worker (Oracle Cloud)

## Purpose

Provide a persistent, isolated browser host for Web Agents such as Gemini Web while keeping browser identity and credentials outside AgentOS Core.

This is an experimental/shadow design for `feature/state-kernel-v2`. It does not activate production Oracle services.

## Important compatibility note

The currently wrapped upstream `ai-browser-bridge` project documents macOS as a prerequisite. AgentOS therefore treats `agentos_node/ai_browser_bridge.py` as a transport contract, not proof that the upstream implementation is Linux-ready.

A Linux deployment must use either:

1. a Linux-compatible bridge implementing the same semantic `ask/search` contract; or
2. a Linux port/fork that is live-verified against the signed-in provider UI.

Do not promote a bridge merely because deterministic adapter tests pass.

## Target topology

```text
Oracle Cloud VM
├─ AgentOS Core                    (no browser credentials)
├─ Provider Bridge                 (semantic routing only)
└─ Browser Worker boundary
   ├─ dedicated Linux user/container
   ├─ Chrome/Chromium
   ├─ persistent non-default profile
   ├─ X11/Wayland/Xvfb display
   └─ Linux-compatible browser bridge
       ├─ gemini
       ├─ chatgpt
       └─ other explicitly verified providers
```

The browser profile is the browser-session SSOT. It must not live under AgentOS Data Layer, Cognitive Kernel storage, repository paths, or GitHub Actions artifacts.

## Governance boundary

- AgentOS Core never reads browser cookies or profile files.
- Browser Worker receives only capability-scoped semantic requests.
- Provider output is untrusted until normalized through the existing WebAgentAdapter/Provider Bridge path.
- No generic remote shell is introduced.
- Initial use is shadow/read-only.
- Login, CAPTCHA and 2FA remain explicit operator actions.
- A provider UI selector change is a runtime failure, not permission to broaden automation privileges.

## Readiness probe

`agentos_node.browser_worker_probe.probe_browser_worker()` performs a non-mutating host check for:

- Linux platform
- Chrome/Chromium executable
- configured bridge executable
- persistent writable profile directory
- DISPLAY or WAYLAND_DISPLAY

The probe deliberately does not create directories, start Chrome, read the profile, or test provider sessions.

## Oracle acceptance sequence

### Gate 0 — host isolation

Create a dedicated browser-worker identity/container. AgentOS Core must not have direct read permission to the browser profile.

### Gate 1 — static readiness

Run the read-only readiness probe. All requirements must pass before browser launch.

### Gate 2 — operator login

Launch Chrome/Chromium with a persistent, non-default profile and complete Gemini login manually through the remote desktop/display surface.

### Gate 3 — local semantic smoke test

From the Browser Worker boundary only, send a harmless prompt such as `reply exactly: pong` and verify semantic JSON output. Do not ingest it into durable memory yet.

### Gate 4 — AgentOS shadow route

Register `gemini-web-shadow` for a non-mutating capability such as `ai.verify.shadow`. Route one bounded task through Provider Bridge and confirm:

```text
exact task lease
→ browser semantic request
→ normalized provider result
→ task completion
```

### Gate 5 — provenance/experience check

Verify that the result records provider/runtime provenance and remains candidate evidence. Browser output must not become canonical ProjectState directly.

### Gate 6 — limited promotion

Only after repeated live verification may the route advertise normal reasoning/research capabilities. High-impact external actions remain blocked until SideEffect Ledger and corresponding GovernanceGate exist.

## Why GitHub-hosted Actions is not the browser identity

GitHub-hosted runners are ephemeral and are appropriate for orchestration/CI, not for holding a long-lived signed-in browser profile. A self-hosted runner may wake a persistent Browser Worker, but the browser identity remains inside the worker boundary.

Recommended separation:

```text
GitHub Actions  = orchestration / verification / wake-up
Browser Worker  = persistent browser identity / provider UI
AgentOS Core    = state / cognition / governance
```

## Next implementation boundary

The next safe code step is a Linux bridge runtime implementing the already-tested semantic contract. Provider-specific DOM automation must remain outside AgentOS Core and requires live signed-in verification before it is considered supported.
