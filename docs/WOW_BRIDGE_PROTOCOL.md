# WoW Bridge: bounded offline pixel protocol

This commit only implements an independent pure-Python binary pixel frame codec and a constrained single-action request decoder. It follows the upstream documented 0xC7 0x1A framing, 3-bit RGB cells and Fletcher-16, with a 512-byte cap. Only `wow.control.status` is accepted. Incoming pixels are **not authentication**. Duplicate IDs are tracked only in-memory; durable runtime idempotency is still required.

The OfflineStatusGateway ALWAYS returns `ONE_NOT_BOUND`. No live Node/ONE reader, captured WoW screen, credential, authenticated local session, game-side pixel strip, slot reply, executable Bridge or receipt exists here. This is a codec/test increment only, not a working bidirectional link.

The next work is game-side encoding and a Windows screenshot capture probe with a pinned supported client, followed by ONE-authorized local reader and load-on-demand return channel. Do not reuse upstream direct CLI or unrestricted permissions.

Capture framing hardening: decoders now allow zero-only display padding after a declared complete packet, but reject nonzero residual bits and any unexpected trailing colored cell, including non-integer/boolean cell types. This is an integrity boundary only, not authentication or evidence of a live Bridge.

## Host-only status binding (candidate; not deployed)

`NodeBoundStatusGateway` provides a unit-testable **host-side** seam between a decoded, read-only `wow.control.status` request and the existing Node adapter. It requires an injected trusted Node authorization callback returning the boolean `True` on every request and an injected read-only adapter callback. It never interprets the game-provided session as authorization, never forwards that session to the adapter, and never invokes arbitrary actions. Unknown or unsafe response fields are rejected through the canonical WoW projection. Request replay is denied in memory; after a bounded history fills, it fails closed instead of evicting prior IDs.

This is not a deployed Windows service, not a verified Node identity or Realm, not a screen capture transport, and not a game-side response channel. A production integration must bind the callback to a **fresh authenticated Node/ONE state check** in the existing Windows Node, persist appropriate idempotency across restarts and establish a verified game-compatible response mechanism. A successful mocked unit test MUST NOT be reported as an actual in-game exchange or ONE Receipt.

## Correlated status reply codec (source-only)

`agentos_node/wow_status_reply.py` now provides a transport-neutral, bounded
`agentos.wow.status.reply/v1` envelope (maximum 384 bytes), encoding an
allowlisted status snapshot together with the original request ID. Its decoder
rejects wrong IDs, unexpected fields, unsupported schema/status, malformed
values and oversized payloads. The existing Transport Routing Guard test step
includes `tests.test_wow_status_reply`.

**This is not a game reply transport.** Before sending any payload back to the
Addon, the host must authenticate its own Windows Node/Realm state, verify the
actual ONE status route, and bind a version-compatible, user-authorized reply
mechanism. The codec alone does not authenticate a sender, install Addon files,
deliver status into WoW, or supply a real Receipt.

## Host-side atomic slot publisher (candidate)

`agentos_node/wow_slot_publisher.py` now connects the existing
`NodeBoundStatusGateway` to the existing bounded reply renderer. The caller
must supply an already-authorized host gateway and the specifically
preinstalled `AgentOSWoW_R001` directory. An unauthorized/replayed/mismatched
request does not modify the slot. A valid response produces **data-only** Lua
and uses a same-directory temporary file plus atomic replace of `Reply.lua`;
the helper will not create addon directories, install a TOC, follow a symlinked
slot file, write arbitrary filenames, or embed any executable/secret-bearing
Node response. Regression tests are registered in the existing Transport
Routing Guard.

**Unverified production boundaries:** Python unit tests do not establish a
Windows deployment or an authenticated Node/ONE route. The trusted Windows
caller must verify the installed game root and Realm/Node identity, protect
the slot directory against untrusted modification, isolate publisher
permissions, maintain durable replay handling, and validate the Addon's
actual load-on-demand refresh behavior on the pinned game client. Atomic
replacement is not itself cross-process synchronization or an end-to-end
Receipt; do not mark MVP ready on code/CI alone.

## Read-only Node heartbeat Bridge seam (source-only, 2026-11-14)

`agentos_node/wow_bridge_once.py` now composes the existing bounded RGB
status decoder, trusted Node-bound gateway and preinstalled reply-slot
publisher into one *opt-in, single-request* host entry. A trusted Windows
host supplies the installed Node config/policy and exact AddOn reply-slot
path. The entry requires a **fresh authenticated ONE heartbeat response**
(`heartbeat_recorded is True`) before publishing `NODE_ONLINE` with
`paw=unverified` and no Receipt. Denied/missing/failed heartbeats never
change the Lua reply file. No payload or reply includes the host Node
credential, session secret, OAuth cookie or Realm selector.

**Not a deployable resident Bridge:** there is still no persistent process
capturing WoW screen frames, no production Node callback attestation, no
signed installer including this helper, no verified Load-on-Demand game reply,
no task summary or read-only ONE status Reader, and no general question/answer
path. Do not equate `NODE_ONLINE` with completion of the game-to-ONE MVP.
Use this source seam as the minimal next Windows live test boundary; keep
work on existing #2134/#2135, with backend account pairing #2264.


### Single-shot real Windows path (source candidate, NOT official installed Bridge)

The host-only wrapper `scripts/wow_agentos_bridge_once.ps1` connects the
existing pixel capture (`-OutputCellsJson`) to `wow_bridge_once.py`, using
the existing Node config/policy. It insists on the expected WoW Forever game
executable, existing installed status Reply slot, real game window and fresh
authenticated ONE Node heartbeat. It may publish a single correlated,
data-only status reply showing **Node ONLINE only**; it does not publish a Paw
state, work receipt, user account, full Runtime status or chat. The Lua
`Read reply slot (once)` is still needed, with one-shot reload constraints.

This is a **source-only integration harness** for the authorized Windows
acceptance owner, not a signed installer component, resident Windows service,
background poller or a publicly usable update. The official one-click installer
must include verified Bridge installation, managed process lifecycle,
account/Realm pairing, durable replay and genuine ONE task/receipt readback
before this can be promoted. Do not advise the player to run this from random
ZIPs or claim the previous screenshot represents a verified Bridge.
