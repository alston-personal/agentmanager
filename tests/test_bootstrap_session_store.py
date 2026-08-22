from datetime import datetime, timezone

import pytest

from agent_core.bootstrap_session_store import BootstrapSessionError, BootstrapSessionStore


def test_bootstrap_session_is_hashed_scoped_and_single_use(tmp_path) -> None:
    store = BootstrapSessionStore(
        str(tmp_path / "sessions.db"),
        now=lambda: datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc),
    )
    _, token, _ = store.issue(node_id="node-a", ttl_minutes=10)
    assert token.encode() not in (tmp_path / "sessions.db").read_bytes()
    assert store.authenticate(token, required_scope="onboarding.submit") == "node-a"
    assert store.authenticate(token, required_scope="onboarding.submit", consume=True) == "node-a"
    with pytest.raises(BootstrapSessionError, match="already consumed"):
        store.authenticate(token, required_scope="onboarding.submit")


def test_bootstrap_session_rejects_scope_and_expiry(tmp_path) -> None:
    current = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)
    store = BootstrapSessionStore(str(tmp_path / "sessions.db"), now=lambda: current)
    _, token, _ = store.issue(node_id="node-a", ttl_minutes=1)
    with pytest.raises(BootstrapSessionError, match="scope mismatch"):
        store.authenticate(token, required_scope="node.external.act")

    expired = BootstrapSessionStore(
        str(tmp_path / "sessions.db"),
        now=lambda: datetime(2026, 8, 22, 12, 2, tzinfo=timezone.utc),
    )
    with pytest.raises(BootstrapSessionError, match="expired"):
        expired.authenticate(token, required_scope="onboarding.submit")
