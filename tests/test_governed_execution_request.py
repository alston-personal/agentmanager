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


def vendor_request(**changes):
    value = {
        "schema": "agentos.execution-request/v1",
        "request_id": "vendor-production-runtime-" + "b" * 40,
        "project_id": "vendor-reputation-service",
        "repository": "alston-personal/vendor-reputation-service",
        "source_ref": "main",
        "source_sha": "b" * 40,
        "capability": "vendor.production.runtime.inspect",
        "environment": "production",
        "parameters": {"listen_port": 18765},
        "replay_policy": "idempotent",
        "expected_result": "agentos.execution-receipt/v1",
    }
    value.update(changes)
    return value


def test_exact_typed_request_resolves_authority():
    project, capability = MODULE.resolve_authority(request(), registry())
    assert project["repository"] == "alston-personal/leopardcat-tarot"
    assert capability["adapter"] == "leopardcat_production_parity_inspect"


def test_second_product_resolves_generic_runtime_inspector():
    project, capability = MODULE.resolve_authority(vendor_request(), registry())
    assert project["repository"] == "alston-personal/vendor-reputation-service"
    assert capability["adapter"] == "repository_service_inspect"
    assert capability["runtime"]["repo_root"] == "/home/ubuntu/vendor-reputation-service"
    assert capability["runtime"]["health_path"] == "/healthz"


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


def test_vendor_cannot_select_leopardcat_capability():
    try:
        MODULE.resolve_authority(vendor_request(capability="leopardcat.production.parity.inspect"), registry())
    except RuntimeError as exc:
        assert "not authorized for project" in str(exc)
    else:
        raise AssertionError("cross-product capability substitution must be rejected")


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


def test_vendor_parameter_widening_is_rejected():
    try:
        MODULE.resolve_authority(vendor_request(parameters={"listen_port": 22}), registry())
    except RuntimeError as exc:
        assert "typed capability" in str(exc)
    else:
        raise AssertionError("Vendor request cannot retarget a privileged listener")


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


def test_runtime_branch_policy_is_explicit_and_bounded():
    assert MODULE.branch_matches_policy("main", "main", "source_ref") is True
    assert MODULE.branch_matches_policy("", "main", "detached_or_source_ref") is True
    assert MODULE.branch_matches_policy("main", "main", "detached_or_source_ref") is True
    assert MODULE.branch_matches_policy("feature/unsafe", "main", "detached_or_source_ref") is False
    try:
        MODULE.branch_matches_policy("main", "main", "anything")
    except RuntimeError as exc:
        assert "unsupported runtime branch policy" in str(exc)
    else:
        raise AssertionError("unknown runtime branch policy must fail closed")


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
