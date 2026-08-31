from datetime import datetime, timedelta, timezone

from agent_core.durable_test_run import DurableTestRun, JsonTestRunStore, TestRunState


def iso_after(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def test_fault_test_cannot_expect_offline_before_recovery_is_armed():
    run = DurableTestRun('run-1', 'disconnect recovery', ['node-a'])
    try:
        run.expect_offline('node-a', reconnect_deadline=iso_after(60))
    except RuntimeError as exc:
        assert 'recovery is armed' in str(exc)
    else:
        raise AssertionError('expected RuntimeError')


def test_run_survives_store_round_trip(tmp_path):
    run = DurableTestRun('run-2', 'reboot recovery', ['node-a', 'node-b'])
    run.transition(TestRunState.PREFLIGHT, step='preflight')
    run.arm_recovery('node-a', {'action': 'node.reconnect', 'expires_at': iso_after(180)})
    run.expect_offline('node-a', reconnect_deadline=iso_after(180))

    store = JsonTestRunStore(tmp_path)
    store.save(run)
    restored = store.load('run-2')

    assert restored is not None
    assert restored.state == TestRunState.WAITING_OFFLINE
    assert restored.expected_offline_nodes == ['node-a']
    assert restored.recovery_plans['node-a']['action'] == 'node.reconnect'


def test_online_observation_resumes_run():
    run = DurableTestRun('run-3', 'reboot recovery', ['node-a'])
    run.arm_recovery('node-a', {'action': 'node.reconnect', 'expires_at': iso_after(180)})
    run.expect_offline('node-a', reconnect_deadline=iso_after(180))
    run.observe_online('node-a', boot_id='boot-new')

    assert run.state == TestRunState.RUNNING
    assert run.expected_offline_nodes == []
    assert run.checkpoints[-1].details['boot_id'] == 'boot-new'
