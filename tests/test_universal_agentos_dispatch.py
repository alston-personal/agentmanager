from pathlib import Path


def test_universal_dispatch_workflow_has_no_execution_target():
    text=Path(".github/workflows/agentos-dispatch.yml").read_text(encoding="utf-8")
    assert "workflow_call:" in text
    assert "workflow_dispatch:" in text
    assert "capability:" in text and "operation:" in text
    assert "scripts/agentos_dispatch.sh" in text
    assert "audience=agentos-scheduler" in text
    assert "self-hosted" not in text
    assert "oracle-gui" not in text
    assert "oracle-control" not in text


def test_reusable_acceptance_knows_only_public_intent():
    text=Path(".github/workflows/universal-agentos-dispatch-acceptance.yml").read_text(encoding="utf-8")
    assert "uses: ./.github/workflows/agentos-dispatch.yml" in text
    assert "capability: agentos.dispatch" in text
    assert "operation: probe" in text
    assert "runs-on:" not in text


def test_dispatch_client_accepts_json_payload_without_runner_selector():
    text=Path("scripts/agentos_dispatch.sh").read_text(encoding="utf-8")
    assert "--payload-json" in text
    assert "payload JSON must be an object" in text
    assert "oracle-gui" not in text
    assert "oracle-control" not in text
