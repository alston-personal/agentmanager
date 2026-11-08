# WoW Bridge: bounded offline pixel protocol

This commit only implements an independent pure-Python binary pixel frame codec and a constrained single-action request decoder. It follows the upstream documented 0xC7 0x1A framing, 3-bit RGB cells and Fletcher-16, with a 512-byte cap. Only `wow.control.status` is accepted. Incoming pixels are **not authentication**. Duplicate IDs are tracked only in-memory; durable runtime idempotency is still required.

The OfflineStatusGateway ALWAYS returns `ONE_NOT_BOUND`. No live Node/ONE reader, captured WoW screen, credential, authenticated local session, game-side pixel strip, slot reply, executable Bridge or receipt exists here. This is a codec/test increment only, not a working bidirectional link.

The next work is game-side encoding and a Windows screenshot capture probe with a pinned supported client, followed by ONE-authorized local reader and load-on-demand return channel. Do not reuse upstream direct CLI or unrestricted permissions.
