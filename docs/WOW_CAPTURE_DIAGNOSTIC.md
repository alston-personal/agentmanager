# Windows one-shot WoW pixel capture (diagnostic candidate)

- On a *verified supported* Windows WoW client, open `/agentos` then click **Status probe**.
- From a checked-out AgentOS repo, run PowerShell `scripts/capture_wow_status_probe.ps1` while the pixel strip remains visible (20 seconds).
- For a screenshot sample, use `-TestImage <path>`; still only decodes and does not send a request to ONE.
- Output `DECODED_UNAUTHORIZED` proves a correctly framed, checksum-valid status packet was captured, but **not** Node/Realm authentication, game-client identity, connected Bridge, live ONE data or receipt. A random/no packet is rejected. Source test `tests/test_wow_capture_probe.py` validates decoder behavior without a real WoW client.

**Live gate missing:** Real-game 800×4 top-left pixel placement, UI scaling, authorized game process binding, continuous capture, durable dedup, local Node/ONE authentication and returning a response to a game Addon slot. This is deliberately NOT an executable service, and never runs a model or arbitrary CLI command. Do not mistake this developer probe for a released installer.
