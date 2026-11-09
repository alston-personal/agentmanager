# WoW Bridge: bounded offline pixel protocol

This commit only implements an independent pure-Python binary pixel frame codec and a constrained single-action request decoder. It follows the upstream documented 0xC7 0x1A framing, 3-bit RGB cells and Fletcher-16, with a 512-byte cap. Only `wow.control.status` is accepted. Incoming pixels are **not authentication**. Duplicate IDs are tracked only in-memory; durable runtime idempotency is still required.

The OfflineStatusGateway ALWAYS returns `ONE_NOT_BOUND`. No live Node/ONE reader, captured WoW screen, credential, authenticated local session, game-side pixel strip, slot reply, executable Bridge or receipt exists here. This is a codec/test increment only, not a working bidirectional link.

The next work is game-side encoding and a Windows screenshot capture probe with a pinned supported client, followed by ONE-authorized local reader and load-on-demand return channel. Do not reuse upstream direct CLI or unrestricted permissions.

Capture framing hardening: decoders now allow zero-only display padding after a declared complete packet, but reject nonzero residual bits and any unexpected trailing colored cell, including non-integer/boolean cell types. This is an integrity boundary only, not authentication or evidence of a live Bridge.

## Host-only status binding (candidate; not deployed)

`NodeBoundStatusGateway` provides a unit-testable **host-side** seam between a decoded, read-only `wow.control.status` request and the existing Node adapter. It requires an injected trusted Node authorization callback returning the boolean `True` on every request and an injected read-only adapter callback. It never interprets the game-provided session as authorization, never forwards that session to the adapter, and never invokes arbitrary actions. Unknown or unsafe response fields are rejected through the canonical WoW projection. Request replay is denied in memory; after a bounded history fills, it fails closed instead of evicting prior IDs.

This is not a deployed Windows service, not a verified Node identity or Realm, not a screen capture transport, and not a game-side response channel. A production integration must bind the callback to a **fresh authenticated Node/ONE state check** in the existing Windows Node, persist appropriate idempotency across restarts and establish a verified game-compatible response mechanism. A successful mocked unit test MUST NOT be reported as an actual in-game exchange or ONE Receipt.
