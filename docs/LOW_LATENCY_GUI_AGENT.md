# Low-latency GUI Agent

Status: implementation in progress

## Goal

Turn a Realm-enrolled Windows Node into a governed interactive executor that can act as the "hands and eyes" of a reasoning Agent without routing every click through GitHub Actions.

Target control path:

```
Reasoning Agent
  -> AgentOS Realm
  -> long-poll task channel
  -> Windows Thin Client
  -> local desktop plan executor
  -> receipt/checkpoint
```

GitHub remains a deployment, governance and audit surface, not the per-click runtime transport.

## Implemented in this change

- `/v1/tasks?wait_seconds=N` supports bounded long polling.
- Thin Client no longer sleeps five seconds between normal task polls.
- `desktop.plan.execute` executes a bounded sequence locally on the Node.
- desktop text input automatically uses Unicode clipboard paste for non-ASCII or long text, avoiding IME dependency.
- URL navigation remains a semantic desktop action and should not be typed through the keyboard.

## Safety boundary

A local plan is intentionally bounded. It may contain only allowlisted desktop actions and stops on the first error by default. Shell execution is not implicitly available inside a GUI plan. High-impact actions can therefore remain separate governed tasks or require explicit approval policy.

## Remaining path to persistent interactive sessions

Long polling removes the dominant fixed delay while preserving the current HTTP/gateway model. A later transport revision may use WebSocket/SSE, but the semantic contract should remain the same:

- one active session/lease per interactive desktop;
- ordered plan steps;
- explicit checkpoints;
- receipts with elapsed time and failed step;
- cancellation;
- lease expiry and recovery;
- capability and policy checks at the Node.

## Known bottlenecks

1. Application response time: model generation, image generation, uploads and page rendering remain external latency.
2. UI drift: labels, accessibility trees and layouts change. Semantic skills need selectors plus fallback strategies.
3. Visual ambiguity: canvas/WebGL/remote-desktop content may not expose an accessibility tree and requires vision.
4. Session state: login expiry, 2FA, passkeys, CAPTCHA and account challenges can require human intervention.
5. Focus and desktop state: popups, file dialogs, monitor topology, lock screen, RDP session changes and user mouse activity can steal focus.
6. Concurrency: two agents controlling one interactive session must be prevented by a lease/mutex.
7. Destructive actions: publishing, purchases, deletes and production changes need policy gates and evidence.
8. Recovery: partial progress must be checkpointed so a browser crash or node restart does not repeat irreversible steps.
9. Anti-automation defenses: some sites may block or challenge automated interaction even when operated through a real GUI.
10. Human-level judgment: subjective visual QA, subtle UX quality and ambiguous product intent still benefit from a reasoning checkpoint rather than blind local execution.
