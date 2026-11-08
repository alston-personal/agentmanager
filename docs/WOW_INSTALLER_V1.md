# WoW AgentOS installer preflight — candidate only

The Windows double-click preflight lives at `scripts/WoW-AgentOS-Setup.cmd`, which runs the read-only `wow_agentos_installer_preflight.ps1`.

It distinguishes missing Node, unenrolled Node, invalid enrollment, existing authenticated Node, unreachable Node, mismatched Realm, and unsupported WoW client. **No game file is installed** and no Realm credential is altered.

To inspect a custom game directory: `powershell -File scripts/wow_agentos_installer_preflight.ps1 -WowRoot "C:\\Games\\World of Warcraft" -Json`.

## Required for production one-click installer
- Complete user-facing official-site `/join` logged-in approval flow, reuse existing Node `join` request/status/claim.
- Version-pinned, verified compatible WoW Addon and local Bridge that talk only through governed ONE status route.
- Integrate the existing Node bootstrap only after consent, not if a Node is merely offline.
- Host a versioned downloadable, SHA256-verified signed installer on official site with staged rollback.
- Prove Windows real game install, same-Realm reuse, new Node enrollment, blocked cross-Realm without mutation, uninstallation, and an actual ONE receipt.
- No finished installer, public download, or WoW status receipt is claimed by this change.
