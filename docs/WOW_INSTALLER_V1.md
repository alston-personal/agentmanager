# AgentOS WoW V1 Windows offline Addon installer — preview, NOT official release

The original preflight remains at `scripts/wow_agentos_installer_preflight.ps1`.
The new local **offline Addon installer** is `scripts/wow_agentos_install.ps1`,
with a double-click entry `scripts/WoW-AgentOS-Setup.cmd`.

This is a candidate source implementation, **not yet a finished signed
download or an authenticated WoW ↔ ONE Bridge**. Do not publish to the official
website until the full acceptance gates below pass.

## Supported installation scope

- Target: an explicitly selected existing WoW root containing
  `_forever_/Wow.exe`, `_forever_/Interface/AddOns/`. Retail/Classic remain
  unverified and are rejected.
- Prerequisite: existing enrolled Windows AgentOS Node, matching Realm/ONE URL,
  and existing `agentos-client.cmd verify` returns success. No new Node
  enrollment, realm switching or credential mutation.
- Requires WoW to be closed and explicit interactive `INSTALL` approval
  (or an explicitly supplied `-ConfirmInstall` opt-in from trusted automation).
- Installs only `AgentOSWoW` and `AgentOSWoW_R001`, from the bundled
  `integrations/wow/` directory. Refuses to overwrite existing addon folders.
- Stages both folders under AddOns; compares SHA-256 of copied files and
  attempts rollback of only newly installed folders on error.
- Offline UI: `/agentos` panel, status probe, one-shot reply slot reader.
  No installed, connected or authenticated Bridge/executor is claimed.

## Manual preview invocation from a complete source checkout

```powershell
powershell -NoProfile -File scripts/wow_agentos_install.ps1 -Mode Install -WowRoot "C:\Games\World of Warcraft"
powershell -NoProfile -File scripts/wow_agentos_install.ps1 -Mode Uninstall -WowRoot "C:\Games\World of Warcraft"
```

Uninstall is intentionally fail-closed: refuse to remove unfamiliar files,
modified addon content or files touched by a live publisher. For an updated
slot, cleanup will require an authorized upgrade/uninstall migration;
do **not** arbitrarily delete game files or existing Node data.

## Required before shipping official installable V1

1. Run the existing Transport Routing Guard + PowerShell syntax and functional
   Windows integration tests. Static Python contract tests are **not** a
   substitute for invoking PowerShell on Windows.
2. Verify the game client and Load-on-Demand API using a real version-pinned
   installation, including launch, display, data slot update, rollback and
   uninstall/reinstall.
3. Bind to the existing authenticated Windows Node and governed ONE Reader;
   confirm 2 genuine correlated game-visible exchanges and formal receipts.
4. Package a complete versioned installer payload with hash manifest and
   signed artifact; validate from a fresh Windows client.
5. Release through the already-governed official AgentOS website route, with
   rollback and published hash/signature; do not display a link before release.

No public download, verified WoW install, authenticated response or official
ONE Receipt is asserted by the source commits.
