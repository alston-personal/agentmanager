# WoW V1 native Addon UI — offline developer shell, not live chat

A native Addon shell exists in `integrations/wow/AgentOSWoW/`.
Open/close the panel with `/agentos`. The chat Send field remains disabled:
there is NO authenticated reply transport, installed local Bridge, verified ONE
reader, official Runtime Receipt, or completed in-game two-way exchange.

The Addon now includes a passive, user-initiated **outbound status pixel probe**
with a bounded frame protocol in `agentos_node/wow_bridge_protocol.py`.
This is **not** an authenticated or deployed channel; a visible pixel frame is
not evidence of successful local capture or Node/ONE connection. The probe's
session text is not an authorization credential, and no arbitrary commands,
execution, permissions or shell access are supported.

The candidate TOC `16001` targets the upstream-documented WoW: Forever
environment only. Its actual running client/API compatibility has not yet
been verified; official Retail/Classic are unsupported pending independent
compatibility tests. Do not advertise an official installer or functional chat.

`wow.control.status` is off by default and fails closed without a trusted
Node-side reader. Its status projection is now strictly constrained to
`state`, `paw` and `receipt` display fields, rejecting unknown and malformed
input; the reader itself must still be authenticated and construct only
non-sensitive canonical data before any game-visible return.

**Next acceptance:** compatible real client, safe passive capture, authenticated
Bridge binding to the already enrolled Windows Node and existing ONE read-only
route, game-compatible reply transport, and two verified in-game exchanges
with canonical correlation/Receipt evidence. No generic upstream CLI gateway.
