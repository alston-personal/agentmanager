# WoW control surface (#2134) — candidate only

This is a **non-deployed read-only contract**, not a working World of Warcraft addon.

- The existing `NodeAdapter` remains the only Node-side adapter contract.
- Opt-in locally using `AGENTOS_NODE_ADAPTERS=agentos_node.wow_control_adapter`; it exposes `wow.control.status` but returns `UNAVAILABLE` until a trusted Node-side reader is injected.
- No automatic registration, Node enrollment, task dispatch, file access, shell, bridge process, command permissions, or connection to ONE occurs.
- This module is not compatible with an actual game client until an independently verified UI/bridge is connected.
- The upstream `chelinho139/wow-ai` README describes WoW: Forever; retail and Classic compatibility are unverified. Its local CLI execution and allow/retry permissions are **not** part of this design.
- Intent submission and Receipt display require separate governed integration and actual node-authoritative acceptance evidence before claiming READY.

Tests: `python -m unittest tests.test_wow_control_adapter`.
