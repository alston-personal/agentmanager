# Legacy Teams unit preservation during Core release

Evidence: immutable Oracle Core deployment [42532972897](https://github.com/alston-personal/agentmanager/actions/runs/42532972897) failed after `core_bundle_preserved_service_recover=teams-commander.service:NOT_ACTIVE`; rollback succeeded. In the exact release `scripts/install_systemd_user.sh` overwrote and restarted `teams-commander.service` using `scripts/teams_bridge.py` as ExecStart, but that file does not exist in the current `main` or `core/integration` source.

**Correction:** the Core installer no longer renders, enables, or restarts this *legacy external* Teams unit. This does not disable or delete an installed unit. The immutable deployment continues to snapshot and verify any pre-existing active `teams-commander.service` and rolls back if a previously active unit disappears. A future owned Teams implementation requires explicit migration, not an invalid systemd unit injected by generic Core installation.

This change makes no claims that Teams is healthy on Oracle; only actual immutable deployment + observed active runtime receipt can establish success. It does not grant workflow control-plane dispatch or WoW executor rights. Continue the existing #470 -> #2134 intake path after proper runtime rollout.
