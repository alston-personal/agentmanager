import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'repair_antigravity_relay_user.sh'
ACTION_INSTALLER = ROOT / 'scripts' / 'install_action_relay_user.sh'


def _text(path: Path) -> str:
    return path.read_text(encoding='utf-8')


class AntigravityRepairContractTests(unittest.TestCase):
    def test_repair_is_branch_aware_and_allowlisted(self):
        text = _text(SCRIPT)
        self.assertIn('SOURCE_REF="${AGENTOS_REF:-main}"', text)
        self.assertIn('EXPECTED_SOURCE_COMMIT="${AGENTOS_SOURCE_COMMIT:-}"', text)
        self.assertIn('main|core/integration|feature/realm-node-fabric-readiness', text)
        self.assertNotIn('core/issue-194-bounded-executor-jobs)', text)
        self.assertIn('git -C "$REPO" fetch --no-tags origin "$SOURCE_REF"', text)
        self.assertIn('SOURCE_REF_HEAD=$(git -C "$REPO" rev-parse FETCH_HEAD)', text)
        self.assertIn('git -C "$REPO" fetch --no-tags origin "$EXPECTED_SOURCE_COMMIT"', text)
        self.assertIn('SOURCE_COMMIT=$(git -C "$REPO" rev-parse FETCH_HEAD)', text)
        self.assertIn('[ "$SOURCE_COMMIT" != "$EXPECTED_SOURCE_COMMIT" ]', text)
        self.assertIn('git -C "$REPO" merge-base --is-ancestor "$SOURCE_COMMIT" "$SOURCE_REF_HEAD"', text)
        self.assertIn('exact runtime source commit is not in governed ref', text)
        self.assertNotIn('runtime source generation mismatch: ref=$SOURCE_REF observed=$SOURCE_COMMIT expected=$EXPECTED_SOURCE_COMMIT', text)
        self.assertNotIn('origin/main:', text)

    def test_transport_repair_does_not_mutate_realm_exact_release(self):
        text = _text(SCRIPT)
        self.assertNotIn('REALM_RUNTIME=', text)
        self.assertNotIn('REALM_UNIT=', text)
        self.assertNotIn('git -C "$REPO" archive "$SOURCE_COMMIT" agent_core', text)
        self.assertNotIn('rm -rf "$REALM_RUNTIME/agent_core"', text)
        self.assertNotIn('systemctl --user restart agentos-realm-fabric.service', text)
        self.assertNotIn('repair_realm_fabric_store.py', text)
        self.assertNotIn('repair_realm_fabric_truncated_tail.py', text)
        self.assertIn('realm_fabric_dependency_health=PASS', text)

    def test_action_runtime_stays_bound_to_same_immutable_generation(self):
        text = _text(SCRIPT)
        self.assertIn('ACTION_RUNTIME="${AGENTOS_ACTION_RUNTIME_ROOT:-/home/ubuntu/.local/share/agentos/action-runtime}"', text)
        self.assertIn('AGENTOS_ACTION_RUNTIME_ROOT="$ACTION_RUNTIME"', text)
        self.assertIn('AGENTOS_ACTION_SOURCE_COMMIT="$SOURCE_COMMIT"', text)

    def test_relay_boundary_uses_authorized_agentos_group_before_worker_start(self):
        text = _text(SCRIPT)
        self.assertIn("ExecStart=/usr/bin/sg agentos -c '/usr/bin/python3 -m agentos_node.antigravity_relay_worker", text)
        unit_section = text.split('cat > "$UNIT" <<EOF', 1)[1].split('EOF', 1)[0]
        self.assertNotIn('NoNewPrivileges=true', unit_section)
        self.assertIn('UMask=0007', unit_section)

    def test_relay_provider_is_explicit_allowlisted_and_not_capsule_controlled(self):
        text = _text(SCRIPT)
        self.assertIn('PROVIDER="${AGENTOS_ANTIGRAVITY_PROVIDER:-claude}"', text)
        self.assertIn('claude|agy', text)
        self.assertIn('Environment=AGENTOS_ANTIGRAVITY_PROVIDER=$PROVIDER', text)
        self.assertIn('antigravity_provider=$PROVIDER', text)

    def test_repair_attests_runtime_source_provider_and_worker_digest(self):
        text = _text(SCRIPT)
        self.assertIn('MANIFEST="$RUNTIME/runtime-provenance.json"', text)
        self.assertIn('WORKER_SHA256=$(sha256sum "$RUNTIME/agentos_node/antigravity_relay_worker.py"', text)
        self.assertIn('"schema": "agentos.runtime-provenance/v1"', text)
        self.assertIn('"source_ref": source_ref', text)
        self.assertIn('"source_commit": source_commit', text)
        self.assertIn('"provider": provider', text)
        self.assertIn('"worker_sha256": worker_sha', text)
        self.assertIn('Environment=AGENTOS_RUNTIME_SOURCE_REF=$SOURCE_REF', text)
        self.assertIn('Environment=AGENTOS_RUNTIME_SOURCE_COMMIT=$SOURCE_COMMIT', text)
        self.assertIn('Environment=AGENTOS_RUNTIME_WORKER_SHA256=$WORKER_SHA256', text)
        self.assertIn('antigravity_runtime_manifest=$MANIFEST', text)

    def test_action_relay_receives_same_immutable_runtime_generation(self):
        text = _text(SCRIPT)
        self.assertIn('AGENTOS_ACTION_SOURCE_REF="$SOURCE_REF"', text)
        self.assertIn('AGENTOS_ACTION_SOURCE_COMMIT="$SOURCE_COMMIT"', text)
        self.assertIn('bash "$TMPDIR/install_action_relay_user.sh"', text)
        self.assertIn('action_relay_source_generation_pinned=PASS', text)

    def test_experience_mcp_is_seeded_and_installed_from_exact_action_runtime(self):
        text = _text(SCRIPT)
        for path in (
            'agent_core/experience.py',
            'agent_core/experience_store.py',
            'agentos_node/experience_mcp_stdio.py',
            'scripts/seed_one_experience.py',
            'scripts/install_codex_experience_mcp_oracle.py',
            'experience/agentos-core-oracle.seed.json',
        ):
            self.assertIn(path, text)
        self.assertIn('cd "$ACTION_RUNTIME"', text)
        self.assertIn('python3 scripts/seed_one_experience.py', text)
        self.assertIn('--seed experience/agentos-core-oracle.seed.json', text)
        self.assertIn('--expected-current-digest "$ONE_EXPERIENCE_EXPECTED_PREDECESSOR"', text)
        self.assertIn('ONE_EXPERIENCE_EXPECTED_PREDECESSOR="sha256:', text)
        self.assertIn('python3 scripts/install_codex_experience_mcp_oracle.py', text)
        self.assertIn('grep -Fq "cwd = \\"$ACTION_RUNTIME\\"" "$CODEX_CONFIG"', text)
        self.assertIn('grep -Fq "PYTHONPATH = \\"$ACTION_RUNTIME\\"" "$CODEX_CONFIG"', text)
        self.assertIn('one_experience_seed=PASS', text)
        self.assertIn('one_experience_digest_convergence=PASS', text)
        self.assertIn('codex_experience_mcp_install=PASS', text)
        self.assertIn('codex_experience_mcp_exact_runtime=PASS', text)
        self.assertNotIn('AGENTOS_EXPERIENCE_MCP_ALLOW_OVERWRITE', text)
        self.assertNotIn('--force', text)

    def test_experience_digest_is_checked_before_action_relay_mutation(self):
        text = _text(SCRIPT)
        marker = 'REPAIR_STAGE="preflight_experience_predecessor"'
        self.assertIn(marker, text)
        self.assertIn('experience_preflight=BLOCKED_PREDECESSOR_MISMATCH', text)
        self.assertIn('experience_preflight=PASS', text)
        self.assertIn('current_digest not in (expected, incoming_digest)', text)
        self.assertLess(text.index(marker), text.index('REPAIR_STAGE="materialize_relay_runtime"'))
        self.assertLess(text.index(marker), text.index('REPAIR_STAGE="install_action_runtime"'))
        self.assertLess(text.index(marker), text.index('systemctl --user restart agentos-antigravity-relay.service'))
        self.assertIn('show_source experience/agentos-core-oracle.seed.json > "$TMPDIR/experience-seed.json"', text)

    def test_action_relay_install_transaction_preserves_prior_generation(self):
        text = _text(ACTION_INSTALLER)
        self.assertIn('action_relay_transaction=SNAPSHOT_READY', text)
        self.assertIn('action_relay_transaction=ROLLED_BACK', text)
        self.assertIn('action_relay_transaction=ROLLBACK_FAILED', text)
        self.assertIn('action_relay_transaction=COMMITTED', text)
        self.assertIn('trap \'rollback_action_relay_install "$?"\' EXIT', text)
        self.assertIn('TXN_OLD_HEAD=$(git -C "$RUNTIME_ROOT" rev-parse --verify HEAD)', text)
        self.assertIn('git -C "$RUNTIME_ROOT" reset --hard "$TXN_OLD_HEAD"', text)
        self.assertIn('cp -p "$TXN_DIR/unit" "$UNIT"', text)
        self.assertIn('cp -p "$TXN_DIR/capabilities" "$CAPABILITY_MARKER"', text)
        self.assertIn('systemctl --user daemon-reload', text)
        self.assertIn('TXN_OLD_ACTIVE', text)
        self.assertIn('TXN_OLD_ENABLED', text)
        self.assertIn('flock -n 9', text)
        self.assertIn('.action-relay-install.pending', text)
        self.assertIn('.action-relay-install.lock', text)
        self.assertIn('action_relay_transaction=INTERRUPTED_RECOVERY_STARTED', text)
        self.assertIn('rollback_action_relay_install 73', text)
        self.assertIn('sync -f "$TXN_DIR/state"', text)
        self.assertIn('TXN_RUNTIME_TOUCHED=1', text)
        self.assertIn('reason=service_remains_active', text)
        self.assertIn('> "$TXN_DIR/state"', text)
        self.assertLess(text.index('action_relay_transaction=SNAPSHOT_READY'), text.index('# Historical Action Relay generations'))
        self.assertLess(text.index('TXN_UNIT_TOUCHED=1'), text.index('cat > "$UNIT"'))
        self.assertNotIn('if [ -n "$LEGACY_BACKUP" ]', text)

    def test_action_relay_installer_preserves_correct_foreign_owned_shared_boundary(self):
        text = _text(ACTION_INSTALLER)
        self.assertIn('ensure_shared_dir()', text)
        self.assertIn("group=$(stat -c '%G' \"$path\")", text)
        self.assertIn("owner=$(stat -c '%U' \"$path\")", text)
        self.assertIn('if [ "$group" != agentos ]; then', text)
        self.assertIn('if [ "$owner" != ubuntu ]; then', text)
        self.assertIn('ubuntu cannot repair foreign-owned shared boundary', text)
        self.assertNotIn('chgrp agentos "$RELAY_ROOT" "$RELAY_ROOT/inbox"', text)
        self.assertNotIn('chmod 2770 "$RELAY_ROOT" "$RELAY_ROOT/inbox"', text)


if __name__ == '__main__':
    unittest.main()
