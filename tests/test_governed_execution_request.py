import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "governed_execution", ROOT / "scripts" / "run_governed_execution_request.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def registry():
    return json.loads((ROOT / "governance" / "execution-authority.json").read_text())


def request(**changes):
    value = {
        "schema": "agentos.execution-request/v1",
        "request_id": "leopardcat-production-parity-" + "a" * 40,
        "project_id": "leopardcat-tarot",
        "repository": "alston-personal/leopardcat-tarot",
        "source_ref": "main",
        "source_sha": "a" * 40,
        "capability": "leopardcat.production.parity.inspect",
        "environment": "production",
        "parameters": {"listen_port": 8088},
        "replay_policy": "idempotent",
        "expected_result": "agentos.execution-receipt/v1",
    }
    value.update(changes)
    return value


def test_exact_typed_request_resolves_authority():
    project, capability = MODULE.resolve_authority(request(), registry())
    assert project["repository"] == "alston-personal/leopardcat-tarot"
    assert capability["adapter"] == "leopardcat_production_parity_inspect"


def test_arbitrary_command_field_is_rejected():
    value = request()
    value["command"] = "rm -rf /"
    try:
        MODULE.resolve_authority(value, registry())
    except RuntimeError as exc:
        assert "request keys mismatch" in str(exc)
    else:
        raise AssertionError("generic command tunneling must be rejected")


def test_repository_cannot_be_swapped():
    try:
        MODULE.resolve_authority(request(repository="other/repo"), registry())
    except RuntimeError as exc:
        assert "Project Identity" in str(exc)
    else:
        raise AssertionError("repository substitution must be rejected")


def test_source_ref_cannot_escape_release_lane():
    try:
        MODULE.resolve_authority(request(source_ref="feature/unsafe"), registry())
    except RuntimeError as exc:
        assert "release-lane" in str(exc)
    else:
        raise AssertionError("branch name alone cannot grant authority")


def test_parameter_widening_is_rejected():
    try:
        MODULE.resolve_authority(request(parameters={"listen_port": 22}), registry())
    except RuntimeError as exc:
        assert "typed capability" in str(exc)
    else:
        raise AssertionError("request-controlled privileged parameters must be rejected")


def test_sha_must_be_exact_lowercase_40_char():
    for bad in ("main", "A" * 40, "a" * 39, "a" * 41):
        try:
            MODULE.resolve_authority(request(source_sha=bad), registry())
        except RuntimeError as exc:
            assert "40-char SHA" in str(exc)
        else:
            raise AssertionError(f"invalid SHA accepted: {bad!r}")


def test_remote_userinfo_is_sanitized():
    assert MODULE.sanitize_remote("https://user:secret@github.com/o/r.git") == "https://github.com/o/r.git"


def test_registry_contains_no_generic_shell_adapter():
    text = (ROOT / "governance" / "execution-authority.json").read_text().lower()
    assert '"shell"' not in text
    assert '"argv"' not in text
    assert '"executable"' not in text


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
    print(f"governed_execution_contract_tests=PASS count={len(tests)}")
