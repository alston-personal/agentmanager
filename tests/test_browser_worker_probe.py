from pathlib import Path

import agentos_node.browser_worker_probe as probe_mod


def test_probe_ready_when_linux_browser_bridge_profile_and_display_exist(tmp_path, monkeypatch):
    profile = tmp_path / "profile"
    profile.mkdir()

    monkeypatch.setattr(probe_mod.platform, "system", lambda: "Linux")

    def fake_which(name):
        if name in {"google-chrome", "bridge"}:
            return f"/usr/bin/{name}"
        return None

    monkeypatch.setattr(probe_mod.shutil, "which", fake_which)
    monkeypatch.setattr(probe_mod.os, "access", lambda path, mode: True)

    result = probe_mod.probe_browser_worker(
        profile_dir=str(profile),
        environ={"DISPLAY": ":99"},
    )

    assert result.ready is True
    assert result.browser_executable == "/usr/bin/google-chrome"
    assert result.bridge_executable == "/usr/bin/bridge"
    assert result.display == ":99"
    assert result.issues == ()


def test_probe_fails_closed_without_runtime_requirements(tmp_path, monkeypatch):
    monkeypatch.setattr(probe_mod.platform, "system", lambda: "Linux")
    monkeypatch.setattr(probe_mod.shutil, "which", lambda name: None)

    result = probe_mod.probe_browser_worker(
        profile_dir=str(tmp_path / "missing"),
        environ={},
    )

    assert result.ready is False
    assert "Chrome/Chromium executable not found" in result.issues
    assert "browser bridge executable not found" in result.issues
    assert "persistent browser profile directory does not exist" in result.issues
    assert "no DISPLAY/WAYLAND_DISPLAY is available" in result.issues


def test_probe_does_not_create_missing_profile(tmp_path, monkeypatch):
    missing = tmp_path / "missing-profile"
    monkeypatch.setattr(probe_mod.platform, "system", lambda: "Linux")
    monkeypatch.setattr(probe_mod.shutil, "which", lambda name: "/usr/bin/fake")

    probe_mod.probe_browser_worker(
        profile_dir=str(missing),
        environ={"DISPLAY": ":1"},
    )

    assert not Path(missing).exists()
