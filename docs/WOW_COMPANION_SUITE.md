# WoW Companion Suite — first incremental implementation

Status: **source candidate only**. This is not an installed WoW AddOn, a working AI Bridge, a shipped bundle, or an AgentOS/ONE live Receipt.

## Existing authorities (reuse, do not fork)

- Canonical runtime and governed Node/Realm routing: `agentmanager/main`.
- Existing WoW AgentOS Lua/Bridge and installer: draft PR #2135, **not merged to main**; reconcile by selecting individual current-source changes rather than blindly merging its divergent branch.
- Existing WoW Nav Assist source: recovery, registration, and dedicated repo follow issue #2297. No claim that its repo currently exists.
- Studio WoW AddOn download route is a separate release responsibility. No new download links until signed release and real-client acceptance.

## Current deliverable

`integrations/wow/companion_suite/manifest.json`: structured candidate inventory with first-party modules, optional third-party metadata, profiles, dependencies, and UI mutual exclusions.

`scripts/wow_companion_suite.py`: **read-only profile planning** with safe dependency expansion, invalid module checks, conflict prevention and third-party review list. Never writes to game installation, saved settings or secrets.

`tests/test_wow_companion_suite.py`: reproducible unit tests.

Run:

```bash
python3 scripts/wow_companion_suite.py --profile minimal
python3 scripts/wow_companion_suite.py --profile standard
python3 scripts/wow_companion_suite.py --profile explorer --with moveany
python3 -m unittest tests.test_wow_companion_suite -v
```

## First acceptance for actually playable version

1. Verify the installed game client build (Forever), `.toc` and actual local AddOn folder via read-only Windows inventory. Do not assume `_forever_`.
2. Restore and review existing Nav Assist source, preserving provenance. Rebase only selected applicable code from #2135 onto current main after inspecting security changes; retain Node/Realm OAuth as a separate optional provider.
3. Implement Companion Core in Lua, UI layout, independent read-only Bridge handshake, game-safe action envelope `map.waypoint`, `buff.missing.highlight`, `ai.reply`; no arbitrary Lua execution.
4. BYOK in a *host-side* OS credential store. No keys in WoW SavedVariables or exported diagnostics. Support direct user-provided provider API, local model, and optional AgentOS realm without requiring an AgentOS account.
5. Integrate actual third-party plugin APIs only after version compatibility, license and optional-feature gating. No redistribution by default. Graceful fallback when TomTom/Questie/HandyNotes are absent.
6. Use existing governed installer carrier to backup, stage, check hash, install only owned directories, and rollback on failure; never silently change unrelated AddOns.
7. Real WoW validation: typed question → search with provenance → answer → waypoint on map, plus mage Buff Assist as a passive indicator and user-activated macro. No protected combat automation, automated spellcasts, injected keys, or pixel-based botting.
8. Verify build, CI, Windows install, client UI, bridge results and ONE Receipt independently, then publish Studio download.

## Non-goals and safety

No agent impersonation, no universal permission to operate the player's OS, no auto-rotation or spell automation, no claim that chat subscription grants provider API quota, and no third-party license bypass.


## Host BYOK adapter (source-only candidate)

`scripts/wow_companion_byok.py` implements a bounded **OpenAI Responses API** host-side adapter with a fixed official endpoint, bounded input/output, caller-supplied API key (in-memory only), timeout, disabled provider-side response storage (`store: false`), injectable network transport for offline tests, and sanitized provider errors. It does **not** save keys, create an HTTP listener, browse web content, read WoW state, or communicate with the WoW client yet. Tests: `tests/test_wow_companion_byok.py`.

This first provider always returns `ui.answer`; map coordinates must come from a separately verified game-knowledge source and pass `validate_reply`. Do not treat language-model hallucinated map coordinates as a trusted waypoint.

**Security and product limitations:** `store: false` does not mean provider network traffic is local or exempt from provider retention policies. Users must understand API billing separately from ChatGPT subscriptions. Key custody belongs to a future Windows host credential-store adapter, not the Lua AddOn. Key values must never enter logs, Git, exports, or SavedVariables.

## Branch convergence

Previous PR #2339 branch diverged as main advanced. A non-rewriting merge of current `main` onto the same working branch was produced, with Git compare confirming `behind=0` at that checked main revision; the merge is not itself authorization to deploy or merge. New upstream commits may require another reconciliation.

## Host-local question gateway

`scripts/wow_companion_ingress.py` implements typed, local-host-only `ai.ask` ingress as a **library callback**, not a new HTTP server or pixel transport. A trusted host session verifier must return the boolean `True`, and the API credential is obtained through an injected host callback. Requests have bounded session, ID and question fields, deny unknown executable fields and game commands, and enforce a finite replay fence before provider billing. The BYOK provider is restricted to `ui.answer` and cannot issue waypoints. This does not yet connect to the client; the transport remains under the #2135 source migration. No persistent credential storage or trusted local session capture is present.

## One-shot reply-slot serialization

`scripts/wow_companion_slot.py` produces a strictly data-only `AgentOSWoWReplySlot` Lua assignment for an `ui.answer` after `validate_reply` correlation. Every UTF-8 byte of dynamic text is encoded as a decimal Lua escape to prevent executable source injection. No disk writing, in-game loading, live Bridge, verified Node authorization or rendering is implemented in this slice. The existing #2135 Lua parser recognizes only its status/account schemas and **must be extended and verified** before an answer appears in WoW. Waypoint actions remain blocked until the trusted Nav Assist adapter is integrated. Tests are in `tests/test_wow_companion_slot.py`.

## Game-client source migration checkpoint

The original `integrations/wow/AgentOSWoW/AgentOSWoW.lua` and `.toc`, and the one-shot `AgentOSWoW_R001` LoadOnDemand data slot, were **selectively ported from draft PR #2135** to the reconciled PR #2339 working branch. The `/agentos` window retains status and account probes as source-only, unverified candidates.

The Lua consumer now parses a distinct `agentos.wow.companion.reply/v1` data-only text reply with string request-ID matching, category/length/control-character checks, and one-shot consumption. **It does not establish a pending AI request ID yet**, because no authenticated game-to-host AI question transport has been integrated. The question control remains deliberately disabled; thus there is no claim of live in-game AI interaction or confirmed response. A future implementation must set `expectedAIRequestId` only for the actual player-triggered question, maintain correlation to the trusted host, and validate the transport/slot scheme against the user's actual WoW build.

`tests/test_wow_companion_client_candidate.py` protects the import against loss of original account/status surfaces and accidental activation of unverified AI send. These are static source tests, not proof that Lua executed successfully in the game.
