from __future__ import annotations

import grp
import importlib.util
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "publish_action_relay_capability.py"
spec = importlib.util.spec_from_file_location("publish_action_relay_capability", SCRIPT)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_publisher_refuses_wrong_effective_group(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    marker = tmp_path / "capabilities.json"
    expected_gid = grp.getgrnam("agentos").gr_gid
    monkeypatch.setattr(os, "getegid", lambda: expected_gid + 1)
    with pytest.raises(PermissionError, match="effective group agentos"):
        mod.publish(marker, source_ref="core/integration", source_commit="a" * 40)


def test_publisher_refuses_non_agentos_spool_group(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    marker = tmp_path / "capabilities.json"
    expected_gid = grp.getgrnam("agentos").gr_gid
    monkeypatch.setattr(os, "getegid", lambda: expected_gid)
    real_stat = marker.parent.stat

    class FakeStat:
        st_gid = expected_gid + 1

    monkeypatch.setattr(Path, "stat", lambda self: FakeStat() if self == marker.parent else real_stat())
    with pytest.raises(PermissionError, match="agentos group boundary"):
        mod.publish(marker, source_ref="core/integration", source_commit="a" * 40)


def test_script_is_fixed_capability_publication_surface():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "shell" not in text.lower()
    assert "subprocess" not in text
    assert "capability_marker_payload" in text
    assert "os.getegid()" in text
    assert "tempfile.mkstemp" in text
