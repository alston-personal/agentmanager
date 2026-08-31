import time

import pytest

from agentos_node.recovery_watchdog import IndependentUpdater, RecoveryLease, UpdatePlan, execute_due_recovery


def test_recovery_executes_only_after_expiry():
    now = int(time.time())
    lease = RecoveryLease('lease-1', 'network.reconnect', now + 10, ('cmd', '/c', 'echo ok'))
    calls = []

    assert execute_due_recovery(lease, now_epoch=now + 5, runner=lambda command: calls.append(command) or 0) is False
    assert calls == []

    assert execute_due_recovery(lease, now_epoch=now + 10, runner=lambda command: calls.append(command) or 0) is True
    assert calls == [lease.command]


def test_updater_must_be_independent_process():
    with pytest.raises(ValueError):
        IndependentUpdater(current_pid=10, updater_pid=10)


def test_update_plan_requires_immutable_ref_and_safe_paths():
    plan = UpdatePlan('a' * 40, '/opt/agentos', ('agentos_node/thin_client.py',), ('agentos-client', 'run'))
    updater = IndependentUpdater(current_pid=10, updater_pid=11)
    updater.validate_plan(plan)

    unsafe = UpdatePlan('a' * 40, '/opt/agentos', ('../escape.py',), ('agentos-client', 'run'))
    with pytest.raises(ValueError):
        updater.validate_plan(unsafe)
