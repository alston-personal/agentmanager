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

## Question packet transport candidate

`scripts/wow_companion_frames.py` implements a typed, 200-cell-compatible multi-part question codec aligned with the existing #2135 pixel-strip frame envelope (two magic bytes, frame ID, length, Fletcher-style checksum). It caps each part at 200 RGB cells and full UTF-8 question at 500 bytes, rejects missing/out-of-order/mixed-session frames, and yields a typed `ai.ask` request for the existing host gateway. The 8-byte session is **only a correlation label**, not an authentication token. A checksum is not a signature.

**Not yet live:** Game client Lua emitter and frame pacing/capture acknowledgements are absent; the button remains disabled, and no host-to-game transport or trusted identity is implied. This prevents misleading users with an unacknowledged pixel transmit. The existing game client must pass a real WoW Forever test of its display/screen-capture compatibility before enabling questions.

## Fixed-width capture parser and local receiver

The 200-cell RGB strip used by the existing candidate UI always includes trailing unused cells in an actual screen capture. The protocol decoder now accepts exact **zero-only padding** after a valid packet and fails closed for nonzero trailing cells or malformed checksum. `scripts/wow_companion_receiver.py` accepts one captured frame at a time into one bounded in-flight question, with strict sequential part index, common request/session identifiers, maximum part count and expiry; errors discard partial state.

`PART_CAPTURED` is **not a game ACK**. Without an authenticated, bidirectional host-to-game acknowledgement, it is unsafe to send multiple timed frames and assume they arrived. Do not enable the Lua Ask button or announce successful delivery until the capture driver/pacing, game-window identification and a verified acknowledgement model have real-game tests and rollback coverage.

## Manual Lua diagnostic emitter (source candidate)

The ported `integrations/wow/AgentOSWoW/AgentOSWoW.lua` now has a **Stage question** diagnostic control, together with a **Show next frame** control. This is user-stepped RGB frame visualization for validating the existing packet codec; it is not an automatic delivery mechanism. The staged question is limited to 500 UTF-8 bytes and broken into 54-byte chunks. Every part is encoded with the existing magic bytes, 3-bit cells, an 8-byte correlation session, a numeric question ID, part index/count, and checksum. No game authority is inferred from the session or checksum.

The controls explicitly report that the Bridge is unverified and never announce a successful host capture, model call, or authenticated request. The actual game-to-host capture driver, feedback/acknowledgment, secure Windows API credential store, automatic pacing and live playtest remain blocked. Do not advertise this candidate as usable in-game AI chat.

## Host capture-to-answer adapter

`scripts/wow_companion_bridge_adapter.py` connects the existing bounded frame receiver to `CompanionQuestionGateway` and `render_companion_slot` through injected local-session authorization, BYOK credential getter, and provider. It creates **candidate Lua slot bytes in memory only**, returning `SLOT_READY` with explicit `published=false` and `game_received=false`. It does not open network ports, store credentials, install an AddOn, write files, impersonate the game, or mark a canonical Receipt. Source-only CI tests verify that untrusted sessions cannot incur API calls and replay cannot charge twice.

To close the live loop, reuse #2135's separately governed installed-slot publisher with exact-path/atomic-write protection, add an authenticated Windows screen capture adapter, install candidate with rollback, and independently demonstrate client receipt on WoW Forever before enabling automatic question emission.

## Shared one-shot slot publisher (existing #2135 code reuse)

The candidate branch now selectively includes `agentos_node/wow_slot_publisher.py` from existing PR #2135, extending it through a shared `_atomic_write` helper and `publish_companion_answer` for a previously validated, correlation-checked `ui.answer`. Only an already-installed `AgentOSWoW_R001/Reply.lua` can be atomically replaced after validating the exact slot path, non-symlink TOC and target, and LoadOnDemand metadata. Failures preserve the previous reply and remove temporary files. No new installer, daemon, Realm identity or background execution is introduced. The original status helper's remaining #2135 imports are not yet ported, so it is **not claimed operational**. A publish result means bytes are on disk, not that WoW loaded them or displayed the response. Keep the slot one-shot and player-triggered; require real target-client evidence before any release.

## Opt-in complete host processing (still not a live Windows transport)

`QuestionBridgeAdapter.accept_and_publish` now makes the existing building blocks callable as one bounded host-side operation. A trusted caller submits a decoded RGB capture and a separately authorized exact preinstalled slot directory. Session authorization, provider credentials, answer validation and atomic writing remain distinct checks. On success the method returns `PUBLISHED`, `published=true`, `game_received=false`; the latter cannot be upgraded without real game readback. Tests cover authorized candidate capture → actual temporary slot write → byte readback, plus denied capture → no provider call/no file write. This is filesystem integration evidence under tests, **not Windows game or ONE Receipt evidence**.

## Source-locked ZIP packaging (candidate, no installation)

`scripts/wow_companion_package.py` assembles a deterministic AddOns ZIP **only** when every local source file matches its allowlisted exact SHA-256. This stage does not download, provision a repository, install, or assert game-client compatibility. It fails closed on absent source files (including unrecovered Nav Assist), invalid paths, symlinks, checksum drift, duplicate destinations and missing top-level AddOn `.toc` entries.

Use a separately reviewed JSON source lock with this schema:

```json
{
  "schema": "agentos.wow-suite-source-lock/v1",
  "files": [
    {
      "addon": "ExampleAddon",
      "path": "ExampleAddon.toc",
      "sha256": "REPLACE_WITH_64_LOWERCASE_HEX_DIGITS"
    },
    {
      "addon": "ExampleAddon",
      "path": "ExampleAddon.lua",
      "sha256": "REPLACE_WITH_64_LOWERCASE_HEX_DIGITS"
    }
  ]
}
```

The exact local source layout is `SOURCE_ROOT/ExampleAddon/ExampleAddon.toc` etc. A lock entry alone is not evidence of licensing, a Git release tag, game version, or first-party ownership; source ownership and release provenance must be reviewed separately before distribution.

```bash
python3 scripts/wow_companion_package.py \
  --lock path/to/approved-source-lock.json \
  --sources-root path/to/staged-addons \
  --output out/wow-companion-candidate.zip
python3 -m unittest tests.test_wow_companion_package tests.test_wow_companion_suite -v
```

The output ZIP includes a `WOW_SUITE_BUILD_MANIFEST.json` enumerating names and hashes and reports its own SHA-256. Its status is `source-verified-not-game-validated`. Do not put provider secrets or host bridge credentials in staged AddOns. Do not publish the ZIP to Studio or attempt live installation until real Forever client compatibility and the separate Windows installer rollback acceptance have passed.

**What is still blocked:** Nav Assist original ZIP provenance, exact first-party Repo registration/ownership, accurate product-wide source lock (including approved artifact/tag/build identifiers), actual Windows client build and AddOns path, and in-game validation. This is a build primitive, **not** the final complete Suite.

