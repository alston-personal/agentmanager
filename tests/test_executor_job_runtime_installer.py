from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install_action_relay_user.sh"
REPAIR = ROOT / "scripts" / "repair_antigravity_relay_user.sh"


def test_action_relay_installer_keeps_single_service_and_loads_executor_job_extension():
    text = INSTALLER.read_text(encoding="utf-8")
    assert 'UNIT="$UNIT_DIR/agentos-action-relay.service"' in text
    assert "agentos_node.executor_job_action_relay --root $RELAY_ROOT" in text
    assert "from agentos_node.executor_job_action_relay import ACTION, ACTIONS" in text
    assert "assert ACTION in ACTIONS" in text
    assert "agentos-action-relay-executor" not in text
    assert "agentos-executor-job.service" not in text


def test_action_relay_runtime_is_resolved_once_to_an_immutable_commit():
    text = INSTALLER.read_text(encoding="utf-8")
    assert 'SOURCE_REF="${AGENTOS_ACTION_SOURCE_REF:-main}"' in text
    assert 'EXPECTED_SOURCE_COMMIT="${AGENTOS_ACTION_SOURCE_COMMIT:-}"' in text
    assert "main|core/integration|feature/realm-node-fabric-readiness" in text
    assert 'git -C "$REPO" fetch --no-tags origin "$SOURCE_REF"' in text
    assert 'SOURCE_REF_HEAD=$(git -C "$REPO" rev-parse FETCH_HEAD)' in text
    assert 'git -C "$REPO" fetch --no-tags origin "$EXPECTED_SOURCE_COMMIT"' in text
    assert 'SOURCE_COMMIT=$(git -C "$REPO" rev-parse FETCH_HEAD)' in text
    assert 'if [ "$SOURCE_COMMIT" != "$EXPECTED_SOURCE_COMMIT" ]; then' in text
    assert 'merge-base --is-ancestor "$SOURCE_COMMIT" "$SOURCE_REF_HEAD"' in text
    assert 'git -C "$RUNTIME_ROOT" reset --hard "$SOURCE_COMMIT"' in text
    assert 'worktree add --detach "$RUNTIME_ROOT" "$SOURCE_COMMIT"' in text
    assert 'test "$(git -C "$RUNTIME_ROOT" rev-parse HEAD)" = "$SOURCE_COMMIT"' in text
    assert 'reset --hard origin/main' not in text
    assert 'worktree add --detach "$RUNTIME_ROOT" origin/main' not in text


def test_action_relay_migrates_only_safe_legacy_plain_runtime_without_deleting_it():
    text = INSTALLER.read_text(encoding="utf-8")
    assert 'LEGACY_RUNTIME_ROOT="${RUNTIME_ROOT}.legacy-pre-worktree"' in text
    assert 'test -d "$RUNTIME_ROOT"' in text
    assert 'test ! -L "$RUNTIME_ROOT"' in text
    assert "owner=$(stat -c '%U' \"$RUNTIME_ROOT\")" in text
    assert 'test "$owner" = ubuntu' in text
    assert 'test ! -e "$LEGACY_RUNTIME_ROOT"' in text
    assert 'mv "$RUNTIME_ROOT" "$LEGACY_RUNTIME_ROOT"' in text
    assert 'action_relay_legacy_runtime_migrated=PASS' in text
    assert 'rm -rf "$RUNTIME_ROOT"' not in text
    assert 'non-empty runtime root is not a worktree' not in text


def test_outer_repair_passes_same_generation_to_action_relay_installer():
    text = REPAIR.read_text(encoding="utf-8")
    assert "main|core/integration|feature/realm-node-fabric-readiness" in text
    assert 'SOURCE_COMMIT=$(git -C "$REPO" rev-parse FETCH_HEAD)' in text
    assert 'AGENTOS_ACTION_SOURCE_REF="$SOURCE_REF"' in text
    assert 'AGENTOS_ACTION_SOURCE_COMMIT="$SOURCE_COMMIT"' in text
    assert 'bash "$TMPDIR/install_action_relay_user.sh"' in text
    assert "action_relay_source_generation_pinned=PASS" in text


def test_bootstrap_scheduler_rollout_tracks_executor_job_contract_generation():
    workflow = (ROOT / ".github" / "workflows" / "oracle-bootstrap-scheduler-rollout.yml").read_text(encoding="utf-8")
    installer = (ROOT / "scripts" / "install_bootstrap_scheduler_user.sh").read_text(encoding="utf-8")
    for owned_path in (
        "agent_core/executor_job_contract.py",
        "agentos_node/executor_job_adapter.py",
        "agentos_node/executor_job_action_relay.py",
        "agentos_node/engineering_subagent_provider.py",
    ):
        assert f"'{owned_path}'" in workflow
    assert "git -C \"$REPO\" archive \"$SOURCE_COMMIT\" agentos_node agent_core" in installer
    assert "Environment=PYTHONPATH=$RELEASE" in installer
    assert 'canonical_executor_job_request("engineering.windows-thin-client.fix")' in installer
    assert "ENGINEERING_SUBAGENT_PROVIDERS_REGISTERED is True" in installer
