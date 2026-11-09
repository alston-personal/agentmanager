from agentos_node.onboarding_environment import onboarding_requirements


def test_linux_environment_requires_systemd_user():
    env = {
        "os": "Linux",
        "python": "/usr/bin/python3",
        "git": "/usr/bin/git",
        "service_manager": "systemd-user",
        "package_manager": "apt-get",
    }
    result = onboarding_requirements(env)
    assert result["supported"] is True
    assert result["strategy"]["supervisor"] == "systemd-user"


def test_linux_environment_fails_closed_without_supported_supervisor():
    env = {
        "os": "Linux",
        "python": "/usr/bin/python3",
        "git": "/usr/bin/git",
        "service_manager": "unknown",
        "package_manager": "apt-get",
    }
    result = onboarding_requirements(env)
    assert result["supported"] is False
    assert "linux_systemd_user_unavailable" in result["blockers"]


def test_windows_and_macos_use_distinct_supervisors():
    windows = onboarding_requirements({
        "os": "Windows",
        "python": "python.exe",
        "git": "git.exe",
        "service_manager": "scheduled-task",
        "package_manager": None,
    })
    macos = onboarding_requirements({
        "os": "Darwin",
        "python": "/usr/bin/python3",
        "git": "/usr/bin/git",
        "service_manager": "launchd",
        "package_manager": "brew",
    })
    assert windows["supported"] is True
    assert windows["strategy"]["supervisor"] == "scheduled-task"
    assert macos["supported"] is True
    assert macos["strategy"]["supervisor"] == "launchd"
