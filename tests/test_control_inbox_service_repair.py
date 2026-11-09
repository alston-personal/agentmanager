from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location("control_inbox_service_repair", ROOT / "scripts/control_inbox_service_repair.py")
repair = module_from_spec(spec)
spec.loader.exec_module(repair)

CONFIG = """# Host-owned settings must survive maintenance.
AGENTOS_GITHUB_TOKEN=old_github
AGENTOS_CONTROLLER_TOKEN=old_controller
AGENTOS_CONTROL_REPOSITORY=alston-personal/agentmanager
AGENTOS_CONTROL_ISSUE=50
AGENTOS_CONTROL_ALLOWED_LOGIN=alstonhuang
AGENTOS_ONE_URL=http://127.0.0.1:8780
AGENTOS_CONTROL_ALLOWED_ACTIONS=desktop.session.inspect,persona.oursong.activate
AGENTOS_CONTROL_STATE=/private/durable-state.json
AGENTOS_CONTROL_POLL_SECONDS=7
CUSTOM_HOST_SETTING=retain-this-value
"""


@pytest.fixture
def host(monkeypatch, tmp_path):
    env_path = tmp_path / "control-inbox.env"
    env_path.write_text(CONFIG)
    controller = tmp_path / "controller.env"
    controller.write_text("AGENTOS_CONTROLLER_TOKEN=new_controller\n")
    monkeypatch.setattr(repair, "ENV_PATH", env_path)
    monkeypatch.setattr(repair, "CONTROLLER_PATH", controller)
    monkeypatch.setattr(repair.pwd, "getpwuid", lambda uid: SimpleNamespace(pw_name="ubuntu"))
    calls = []

    def command(args, **kwargs):
        calls.append(args)
        output = str(env_path) + " (ignore_errors=no)\n" if "EnvironmentFiles" in args else ""
        return SimpleNamespace(returncode=0, stdout=output)

    monkeypatch.setattr(repair, "command", command)
    monkeypatch.setattr(repair, "http_status", lambda url, token: 200)
    return env_path, calls


def test_healthy_credentials_are_not_replaced_and_only_bridge_restarts(host, monkeypatch):
    path, calls = host
    monkeypatch.setattr(repair, "github_candidate", lambda: pytest.fail("must not fetch replacement"))
    result = repair.repair()
    assert path.read_text() == CONFIG
    assert result["credentials_changed"] is False
    assert result["end_to_end_verified"] is False
    assert [args[-1] for args in calls if "restart" in args] == [repair.UNIT]


def test_invalid_credentials_are_replaced_without_clobbering_host_configuration(host, monkeypatch):
    path, _ = host
    monkeypatch.setattr(repair, "http_status", lambda url, token: 401 if token.startswith("old_") else 200)
    monkeypatch.setattr(repair, "github_candidate", lambda: "new_github")
    result = repair.repair()
    assert result["credentials_changed"] is True
    assert path.read_text() == CONFIG.replace("old_github", "new_github").replace("old_controller", "new_controller")
    assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("code", [0, 404, 429, 502])
def test_upstream_unavailability_does_not_modify_config_or_restart(host, monkeypatch, code):
    path, calls = host
    monkeypatch.setattr(repair, "http_status", lambda url, token: code if url == repair.ONE_READ else 200)
    with pytest.raises(repair.RepairFailure, match="one_controller_unavailable"):
        repair.repair()
    assert path.read_text() == CONFIG
    assert not any("restart" in args for args in calls)


def test_failed_postcheck_rolls_back_credentials_and_restarts_previous_config(host, monkeypatch):
    path, _ = host
    monkeypatch.setattr(repair, "github_candidate", lambda: "new_github")
    restarts = []
    monkeypatch.setattr(repair, "restart_bridge", lambda: restarts.append(path.read_text()))
    monkeypatch.setattr(repair, "http_status", lambda url, token:
                        401 if token == "old_github" else 502 if token == "new_github" and restarts else 200)
    with pytest.raises(repair.RepairFailure, match="github_postcheck_failed"):
        repair.repair()
    assert path.read_text() == CONFIG
    assert len(restarts) == 2
    assert restarts[-1] == CONFIG


def test_restart_timeout_restores_credentials(host, monkeypatch):
    path, _ = host
    monkeypatch.setattr(repair, "github_candidate", lambda: "new_github")
    monkeypatch.setattr(repair, "http_status", lambda url, token: 401 if token == "old_github" else 200)
    restarts = []

    def restart():
        restarts.append(path.read_text())
        if len(restarts) == 1:
            raise subprocess.TimeoutExpired("systemctl", 20)

    monkeypatch.setattr(repair, "restart_bridge", restart)
    with pytest.raises(subprocess.TimeoutExpired):
        repair.repair()
    assert path.read_text() == CONFIG
    assert len(restarts) == 2


def test_unknown_identity_does_not_create_lock_or_run_commands(host, monkeypatch, capsys):
    path, calls = host
    monkeypatch.setattr(repair.pwd, "getpwuid", lambda uid: SimpleNamespace(pw_name="agentos-node"))
    assert repair.main() == 1
    assert not (path.parent / ".control-inbox-repair.lock").exists()
    assert not calls
    assert "wrong_service_identity" in capsys.readouterr().out


def test_concurrent_configuration_change_is_not_overwritten(host, monkeypatch):
    path, _ = host
    newer = CONFIG + "NEWER_DEPLOYMENT=true\n"

    def candidate():
        path.write_text(newer)
        return "new_github"

    monkeypatch.setattr(repair, "github_candidate", candidate)
    monkeypatch.setattr(repair, "http_status", lambda url, token: 401 if token == "old_github" else 200)
    with pytest.raises(repair.RepairFailure, match="configuration_changed_during_preflight"):
        repair.repair()
    assert path.read_text() == newer


def test_failure_output_does_not_serialize_sensitive_exception(host, monkeypatch, capsys):
    monkeypatch.setattr(repair, "repair", lambda: (_ for _ in ()).throw(RuntimeError("private-token-material")))
    assert repair.main() == 1
    output = capsys.readouterr().out
    assert "private-token-material" not in output
    assert '"error": "repair_failed"' in output


def test_duplicate_environment_keys_fail_closed():
    with pytest.raises(repair.RepairFailure, match="environment_malformed"):
        repair.parse_env("AGENTOS_GITHUB_TOKEN=first\nAGENTOS_GITHUB_TOKEN=second\n")


def test_credential_replacement_cannot_change_allowlist():
    with pytest.raises(repair.RepairFailure, match="credential_update_invalid"):
        repair.replace_credentials(CONFIG, {"AGENTOS_CONTROL_ALLOWED_ACTIONS": "shell.exec"})


@pytest.mark.parametrize("prefix, counts", [
    ("private-fragment\n" * 8, (8, 0, 0)),
    ("CUSTOM_SETTING=value\\\nprivate-fragment\n", (1, 1, 0)),
    ("export private-fragment\n", (1, 0, 1)),
    ("CUSTOM_SETTING=value\\\nexport private-fragment\nsecond-fragment\n", (2, 1, 1)),
])
def test_unsafe_shape_reports_all_structural_counts_without_host_changes(
        host, monkeypatch, capsys, prefix, counts):
    path, calls = host
    original = prefix + CONFIG
    path.write_text(original)
    monkeypatch.setattr(repair, "http_status", lambda *args: pytest.fail("must fail before auth"))
    assert repair.main() == 1
    output = capsys.readouterr().out
    missing, continuation, export = counts
    expected = ("environment_shape_not_safely_normalizable"
                f"_missing_equals_{missing}_prev_cont_{continuation}_exportlike_{export}")
    assert expected in output
    assert "private-fragment" not in output
    assert "second-fragment" not in output
    assert "CUSTOM_SETTING" not in output
    assert "old_github" not in output
    assert path.read_text() == original
    assert not any("restart" in args for args in calls)


def test_single_orphan_normalization_preserves_every_other_line():
    original = "# keep comment\r\n\r\n" + CONFIG.replace("\n", "\r\n")
    malformed = original.replace("AGENTOS_GITHUB_TOKEN=", "private-fragment\r\nAGENTOS_GITHUB_TOKEN=", 1)
    assert repair.normalize_env_shape(malformed) == (original, True)
    assert repair.normalize_env_shape(original) == (original, False)


@pytest.mark.parametrize("count", range(1, 8))
def test_bounded_ignored_lines_preserve_all_other_bytes(count):
    original = CONFIG.replace("\n", "\r\n")
    lines = original.splitlines(keepends=True)
    for index in reversed(range(count)):
        lines.insert(index + 1, "private-fragment\r\n")
    malformed = "".join(lines)
    assert repair.normalize_env_shape(malformed) == (original, True)
    assert repair.parse_env(repair.normalize_env_shape(malformed)[0]) == repair.parse_env(original)


@pytest.mark.parametrize("prefix", [
    'CUSTOM_SETTING="multiline\nprivate-fragment\n"\n',
    "CUSTOM_SETTING='multiline\nprivate-fragment\n'\n",
    "CUSTOM_SETTING=escaped\\ value\nprivate-fragment\n",
    "# comment-continuation\\\nprivate-fragment\n",
    "private-fragment\x00\n",
    "private-fragment\v\n",
    "private-fragment\x85\n",
    "private-fragment\u2028\n",
    "private-fragment\u2029\n",
    "private-fragment\ufeff\n",
    "private-fragment\r",
])
def test_ambiguous_lexical_shape_never_reaches_auth_or_mutation(host, monkeypatch, capsys, prefix):
    path, calls = host
    original = prefix + CONFIG
    path.write_bytes(original.encode("utf-8"))
    monkeypatch.setattr(repair, "http_status", lambda *args: pytest.fail("must fail before auth"))
    assert repair.main() == 1
    output = capsys.readouterr().out
    assert "environment_shape_not_safely_normalizable" in output
    assert "_lexical_unsafe_" in output
    assert "private-fragment" not in output
    assert "CUSTOM_SETTING" not in output
    assert "old_github" not in output
    assert path.read_bytes() == original.encode("utf-8")
    assert not any("restart" in args for args in calls)


def test_seven_ignored_lines_are_repaired_only_after_auth_and_preserve_host_settings(host):
    path, calls = host
    path.write_text("private-fragment\n" * 7 + CONFIG)
    result = repair.repair()
    assert path.read_text() == CONFIG
    assert result["configuration_shape_repaired"] is True
    assert result["configuration_ignored_lines_removed"] == 7
    assert result["credentials_changed"] is False
    assert result["end_to_end_verified"] is False
    assert [args[-1] for args in calls if "restart" in args] == [repair.UNIT]


def test_shape_only_repair_restores_original_bytes_when_postcheck_fails(host, monkeypatch):
    path, _ = host
    original = ("private-fragment\n" * 7 + CONFIG).replace("\n", "\r\n").encode("utf-8")
    path.write_bytes(original)
    restarts = []
    monkeypatch.setattr(repair, "restart_bridge", lambda: restarts.append(path.read_bytes()))
    monkeypatch.setattr(repair, "http_status", lambda *args: 502 if restarts else 200)
    with pytest.raises(repair.RepairFailure, match="github_postcheck_failed"):
        repair.repair()
    assert path.read_bytes() == original
    assert len(restarts) == 2
    assert restarts[-1] == original


@pytest.mark.parametrize("fragment", [
    'private-fragment says "retry"',
    "private-fragment's notice",
    '"private-fragment with an unmatched opening quote',
    "private-fragment with an unmatched closing quote'",
])
def test_quotes_in_independent_ignored_lines_do_not_open_multiline_values(fragment):
    original = CONFIG.replace("\n", "\r\n")
    malformed = original.replace("AGENTOS_GITHUB_TOKEN=", fragment + "\r\n" +
                                 "private-fragment\r\n" * 6 + "AGENTOS_GITHUB_TOKEN=", 1)
    assert repair.normalize_env_shape(malformed) == (original, True)


def test_quoted_comments_are_preserved_byte_for_byte():
    original = '# comment has "quotes" and an apostrophe\'\r\n' + CONFIG.replace("\n", "\r\n")
    assert repair.normalize_env_shape("private-fragment\r\n" * 7 + original) == (original, True)


@pytest.mark.parametrize("prefix, expected", [
    ('CUSTOM_SETTING="multiline\nprivate-fragment\n"\n', "_assignment_quotes_1_assignment_open_quotes_1_ignored_quotes_1"),
    ("CUSTOM_SETTING=value\\\nprivate-fragment\n", "_backslash_1_control_0_bare_cr_0"),
    ("# comment\\\nprivate-fragment\n", "_backslash_1_control_0_bare_cr_0"),
    ("private-fragment\x1b\n", "_backslash_0_control_1_bare_cr_0"),
    ("private-fragment\r", "_backslash_0_control_0_bare_cr_1"),
])
def test_rejection_identifies_structural_class_without_line_contents(host, capsys, prefix, expected):
    path, calls = host
    original = prefix + CONFIG
    path.write_bytes(original.encode("utf-8"))
    assert repair.main() == 1
    output = capsys.readouterr().out
    assert expected in output
    assert "private-fragment" not in output
    assert "CUSTOM_SETTING" not in output
    assert "old_github" not in output
    assert path.read_bytes() == original.encode("utf-8")
    assert not any("restart" in args for args in calls)


@pytest.mark.parametrize("quoted_value", [
    '"retain this value"',
    "'retain this value'",
    '"retain \'single\' quotes too"',
    "'retain \"double\" quotes too'",
])
def test_balanced_assignment_quotes_do_not_block_ignored_line_repair(quoted_value):
    original = CONFIG.replace("CUSTOM_HOST_SETTING=retain-this-value",
                              "CUSTOM_HOST_SETTING=" + quoted_value)
    malformed = "private-fragment\n" * 7 + original
    normalized, changed = repair.normalize_env_shape(malformed)
    assert changed is True
    assert normalized == original
    assert repair.parse_env(normalized)["CUSTOM_HOST_SETTING"] == quoted_value


@pytest.mark.parametrize("assignment", [
    'CUSTOM_HOST_SETTING="unterminated\n',
    "CUSTOM_HOST_SETTING='unterminated\n",
])
def test_open_assignment_quote_still_fails_closed(host, capsys, assignment):
    path, calls = host
    original = assignment + "private-fragment\n" + CONFIG
    path.write_text(original)
    assert repair.main() == 1
    output = capsys.readouterr().out
    assert "_assignment_quotes_1_assignment_open_quotes_1" in output
    assert "private-fragment" not in output
    assert "CUSTOM_HOST_SETTING" not in output
    assert path.read_text() == original
    assert not any("restart" in args for args in calls)
