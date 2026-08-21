from pathlib import Path

from agentos_node.ide_adapter import build_ide_ir, capture_workspace, derive_ide_continuation
from runtime_core.canonical_ir import CanonicalIR


def test_ide_ir_uses_workspace_metadata_without_absolute_path(tmp_path: Path):
    ir = build_ide_ir(
        "review this work",
        workspace=tmp_path,
        project_id="demo",
        capability="code.review",
        provider="gemini",
    )
    assert ir.project_id == "demo"
    assert ir.capability == "code.review"
    assert ir.payload["instruction"] == "review this work"
    assert ir.context["provider_policy"]["preferred_provider"] == "gemini"
    workspace = ir.context["workspace"]
    assert workspace["name"] == tmp_path.name
    assert str(tmp_path) not in str(workspace)


def test_ide_continuation_preserves_state_and_uses_declared_next_capability(tmp_path: Path):
    current = CanonicalIR(
        goal="finish the feature",
        project_id="demo",
        capability="code.implement",
        payload={"result": "implemented"},
        decisions=[{"decision": "use Canonical IR"}],
        continuation={"next_capability": "code.review"},
    )
    next_ir = derive_ide_continuation(current, workspace=tmp_path)
    assert next_ir.parent_ir_id == current.ir_id
    assert next_ir.hop_count == current.hop_count + 1
    assert next_ir.capability == "code.review"
    assert next_ir.decisions == current.decisions


def test_capture_workspace_is_safe_for_non_git_directory(tmp_path: Path):
    snapshot = capture_workspace(tmp_path)
    assert snapshot["name"] == tmp_path.name
    assert snapshot["git"]["isRepository"] is False
    assert snapshot["git"]["dirty"] is False
