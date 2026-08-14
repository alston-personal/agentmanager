import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "docs" / "agentos_ecosystem" / "examples"
SCHEMAS = ROOT / "docs" / "agentos_ecosystem" / "schemas"


def _load_example(name: str) -> dict:
    value = yaml.safe_load((EXAMPLES / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_all_manifest_examples_have_common_envelope():
    expected_kinds = {
        "project.yaml": "Project",
        "module.yaml": "Module",
        "node.yaml": "Node",
        "environment.yaml": "Environment",
    }
    for filename, expected_kind in expected_kinds.items():
        manifest = _load_example(filename)
        assert manifest["apiVersion"] == "agentos/v1"
        assert manifest["kind"] == expected_kind
        assert manifest["metadata"]["id"]
        assert manifest["metadata"]["version"]
        assert isinstance(manifest["spec"], dict)


def test_schema_documents_are_valid_json():
    for schema_path in SCHEMAS.glob("*.json"):
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        assert schema["$schema"].startswith("https://json-schema.org/")
        assert schema["type"] == "object"


def test_project_declares_modules_and_environments():
    manifest = _load_example("project.yaml")
    assert manifest["spec"]["modules"]
    assert manifest["spec"]["environments"] == ["development", "production"]


def test_production_environment_requires_lockfile_and_digest_policy():
    manifest = _load_example("environment.yaml")
    spec = manifest["spec"]
    assert spec["lockfile"]
    assert spec["policies"]["requireArtifactDigest"] is True
