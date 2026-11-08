# WoW V1 native Addon UI — developer shell, not live chat

A small native addon shell is provided in `integrations/wow/AgentOSWoW/`.
It is intentionally offline and read-only until a real, authenticated local
bridge is built and verified. Open/close with `/agentos`. The Send input is
disabled to prevent false success or direct CLI execution.

The TOC `16001` is for the WoW: Forever integration candidate described by
the reviewed upstream project; it is **not** verified for official Retail or
Classic, nor has any real running game session been tested here.

This addon currently has no pixel-strip output, WAV channel, load-on-demand
reply slots, installed bridge, Node status reader or valid live Receipt.
It demonstrates only native interface structure. Do not advertise as a
functional AgentOS game chat or as production-ready.

**Next live gate:** establish one trusted, tightly bounded game-to-local
message transport with request identity, authentication and replay limits,
connect to ONE's already-governed read-only status route, then return an
actual answer and correlation receipt via a game-compatible reply transport.
No generic shell/permissions model from upstream wow-ai may be imported.
