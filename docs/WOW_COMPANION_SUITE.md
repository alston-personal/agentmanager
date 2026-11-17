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
