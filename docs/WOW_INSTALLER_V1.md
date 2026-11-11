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

## Reproducible offline-preview packaging and Windows acceptance

A packaging script now builds an allowlisted, self-contained offline ZIP, not a
repository checkout and not an installer for the authenticated ONE Bridge:

```sh
python scripts/build_wow_offline_installer.py --output dist/AgentOS-WoW-V1-preview.zip
python -m unittest tests.test_wow_offline_packaging -v
```

The ZIP contains only the launcher, PowerShell install/preflight scripts,
`AgentOSWoW` and `AgentOSWoW_R001`, plus `manifest.json` with SHA-256
digests. A companion `.zip.sha256` checks archive integrity. The hash manifest
is **not a digital signature** and must not be represented as authenticating
a release, Node identity or Realm.

The existing `Transport Routing Guard` now includes a `windows-latest`
job that extracts this exact ZIP and runs
`tests/test_wow_offline_installer_windows.ps1` against a synthetic game
directory and mock local Node. It exercises installation, refusal to overwrite,
uninstall, Node preservation and refusal to delete modified files.
Synthetic CI is NOT a real WoW client/ONE handshake and cannot replace the
eventual signed official release with host acceptance receipts.

The workflow artifact is expressly labeled **unverified preview**, retained
temporarily for CI review, and must not be linked or distributed as the
finished official-site installer. Promotion requires Windows CI PASS and
real-client acceptance, governed release approval and signature.

## Install-time package integrity requirement

The installer now refuses installation unless the extracted preview bundle
contains `manifest.json` with the exact required seven payload files and
their matching SHA-256 digests. It rejects missing, malformed, tampered or
symlinked payload files **before** it writes to a game directory. The Windows
functional suite deliberately alters the extracted Addon Lua file, requires
`BUNDLE_HASH_MISMATCH`, checks the game remains untouched, then restores the
package and proceeds with normal installation.

The manifest prevents accidental and undetected changes **relative to the
shipped manifest**, but it is not a trust anchor: both a payload and an unsigned
manifest could be replaced by an attacker. Official release additionally
requires a trusted digital signature and versioned distribution.

The manifest verification requirement means the installer is designed to run
from an extracted ZIP bundle, not directly from a bare source checkout lacking
the generated manifest. No live WoW client, Windows deployment or public
download is claimed by these source changes.

## Root-level Windows entry

The extracted ZIP includes `Install-AgentOS-WoW.cmd` directly at its root.
It delegates to the existing `scripts/WoW-AgentOS-Setup.cmd`; no second
installer, registry changes or privilege escalation is introduced.
Its own content is included in `manifest.json`, so tampering is detected
before game files are modified.

This is an **offline preview**, not an authenticated Bridge or official-site
release. The user still supplies a confirmed Forever game root and approves
installation; the existing Node and Realm are reused unchanged.

## Windows one-click client discovery — 2026-11-10

The ZIP root entry `Install-AgentOS-WoW.cmd` now launches the existing
setup, which uses `scripts/wow_agentos_select_game.ps1` to locate a valid
Forever installation in common Windows paths (including Program Files x86
and common Games directories). If not found, it prompts with the Windows
folder picker. It validates `_forever_/Wow.exe` and the existing AddOns
directory, and refuses a symlink/reparse-point game root. It does not
install or modify a new game client.

The selection helper is included in the allowlisted package manifest and
pre-install SHA-256 verification. The existing Windows runner functional
test now covers choosing a synthetic game root and rejecting an invalid
root without opening a picker.

**Actual CI evidence**: [Transport Routing Guard #42765981178](https://github.com/alston-personal/agentmanager/actions/runs/42765981178)
completed SUCCESS across all three jobs, including
`wow-offline-installer-windows`, with log marker
`WINDOWS_WOW_OFFLINE_INSTALLER=PASS`. The tested ZIP SHA-256 was
`a92f16e15291f3dc93cc83920e35de7d34f1a9bafc8227970f6dc6b19261cd28`.
This remains a synthetic Windows Runner test, not a real player computer,
official signed installer, authenticated ONE Bridge or in-game screenshot.

## Windows PowerShell 5.1 parity — verified CI, 2026-11-10

The double-click `.cmd` entry invokes Windows built-in `powershell.exe`,
not PowerShell 7. The original Windows runner test used `pwsh`, leaving
a real distribution parity gap. The existing `Transport Routing Guard`
now runs its extracted-ZIP functional installer acceptance with the GitHub
Actions `powershell` shell.

Evidence: [Run #42768939292](https://github.com/alston-personal/agentmanager/actions/runs/42768939292),
all three jobs SUCCESS. The Windows install job log explicitly shows
`C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.EXE`,
`WINDOWS_WOW_OFFLINE_INSTALLER=PASS`, and the reproducible ZIP SHA-256
`a92f16e15291f3dc93cc83920e35de7d34f1a9bafc8227970f6dc6b19261cd28`.

This proves the candidate offline installer works with the Windows built-in
shell on a synthetic Forever game directory and mock Node. It **does not**
prove real game client compatibility, host Node/Realm authorization, signed
release or successful official-site distribution. The acceptance gate for
actual WoW game load remains open.

## Real game client acceptance and optional Node Join — 2026-11-10

The user provided a real WoW Forever screenshot showing `/agentos` loading,
the first status probe emitted, and disabled chat. This confirms **the real
game Addon UI loads and sends a local probe**; it does not confirm pixel capture,
trusted local Bridge, ONE reply or working chat. The input is intentionally
disabled in the current Lua Addon until a trusted Bridge exists.

Existing Windows enrollment sources already exist at
`scripts/AgentOS-Join.cmd` and `scripts/bootstrap_clean_windows_node.ps1`.
Do not create a second Node enrollment implementation.

The preview ZIP now contains `Join-AgentOS-Node.cmd` in the root and the
existing `scripts/AgentOS-Join.cmd` source. The wrapper requires the user
to type `JOIN` before invoking the already-governed enrollment/bootstrap
flow, which may download runtime components and require administrator
approval for an enrollment code. After installing the offline Addon, the
setup offers the same opt-in entry **only if the default Node state is absent**.
A detected existing Node is preserved; users with a custom Node location
should reuse that Node and not enroll another identity.

Already-installed Addon users can run `Join-AgentOS-Node.cmd` from the
new ZIP without reinstalling or replacing their Addon. Successful Node Join
is necessary for live bridge routing but **not sufficient** to enable chat:
a local authorized Bridge and game-visible correlated ONE receipts remain
separate acceptance gates. The preview still is not an official signed
release and Node credentials are never packaged into ZIP.

## Single-flow Node installation contract — 2026-11-11

The end-user requirement is **one installation entry**, not a separate
post-install `Join-AgentOS-Node.cmd` instruction. The existing root
`Install-AgentOS-WoW.cmd` now delegates to setup which:

1. Detects a supported game directory, and checks for a complete existing
   `AgentOSWoW` + `AgentOSWoW_R001` installation. Reuses both without
   overwriting. A partial pre-existing installation fails closed.
2. Checks for existing Node enrollment at the default install path. When
   missing, starts the **existing, explicitly confirmed** `AgentOS-Join.cmd`
   within this same user-visible installer flow (via the existing wrapper),
   including the existing ONE Realm approval/code sequence. The user is
   warned to reuse a Node installed elsewhere rather than creating a
   duplicate.
3. When enrollment remains incomplete, explicitly offers **OFFLINE-only**
   continuation; Enter cancels the flow. Nothing asserts a live ONE connection.
4. Only installs the offline Addon if both folders are absent; previously
   installed folders remain unchanged. An authorized Bridge and verified
   game↔ONE receipts remain mandatory before chat can be enabled.

This change does not silently enroll a node, bypass Realm approval, or
auto-install any Bridge. Node creation is user-authorized through the
original AgentOS Join implementation. Existing game Addon installations
do **not** need to be overwritten or reinstalled.

## User session != Node identity — 2026-11-11

Current high-priority request is **sign out of the WoW Addon account then
sign back in as the original account**, selecting that user's authorized
Realm. This is NOT Windows `SwitchRealm`, realm migration, or Node rejoin.
The existing Node remains a transport/capability carrier; its enrollment
does not grant the game user's membership in an arbitrary Realm.

The transport-neutral `agentos_node/client_account_session.py` is a reusable
account-session boundary, NOT a functioning OAuth provider or installed Bridge.
Its trusted host callbacks must come from the existing signed-in AgentOS
site, device pairing and ONE Realm authority. It supports begin/complete
pairing, server-side Realm membership selection and scoped logout with
revocation uncertainty; the public game projection contains only
`signed_in`, safe account display and authorized Realm ID. No OAuth
tokens, Node credentials, ticket, browser cookies, or session handles enter
Lua, SavedVariables, the pixel strip, or untrusted reply-slot data.

The next product integration gate is a *real browser-to-Bridge account pairing*
with the existing OAuth service, server-issued session revocation and a
game-visible account/realm projection. The Addon is still offline with its
Send control disabled; no UI logout/login has shipped yet. Do not claim that
tests of the isolated boundary verify actual OAuth, cross-Realm readback,
Node pairing, or real game switching. Preserve Windows Node credentials and
the existing WoW installation.

## WoW account intent transport (2026-11-11)

The V1 native panel now offers `Sign in via Bridge` and `Sign out via Bridge` buttons.
They emit bounded pixel requests `wow.account.login.start` and
`wow.account.logout`, **not** an account/session/Realm claim. A distinct
host-only `NodeBoundAccountGateway` parses these requests and only delegates
to a trusted injected account handler after explicit fresh host authorization.
No Lua message may specify a Realm ID, account, URL, token, password or path.
Node binding and existing `client.json` are never modified by these actions.
The account-session component is still the separately verified host boundary.

A successfully emitted pixel request is **not** a login, logout, ONE readback
or user-scoped authorization receipt. The live Bridge and existing OAuth
device/browser pairing, revocation acknowledgement, account/Realm projection,
and eventual in-game response transport remain **not yet installed/accepted**.
The UI deliberately continues to state account not signed in, Bridge not
connected, and Send disabled until authenticated replies exist.

Source / regression: Transport Routing Guard CI run 43002028836 (all three
jobs successful) covers the account intent allowlist, denied bridge, replay,
untrusted Realm field, unsafe response data, Addon static safety and bundled
Windows offline installer. CI is not a replacement for a real WoW host test.
