import json
from pathlib import Path
import subprocess
import sys


SCRIPT = Path("scripts/shadow_reconcile_relations.py")
SEED = Path("config/relational-seeds/agentos-zeus-writer.json")


def run_cli(*args: str):
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(SEED), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_real_seed_reconciles_and_resolves_conversational_focus():
    result = run_cli("--focus", "同源雙模小說", "--trigger-ref", "test:zeus")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["mode"] == "shadow"
    assert payload["trigger_ref"] == "test:zeus"
    assert payload["entity_ids"] == ["project:zeus-writer"]


def test_unresolvable_focus_fails_closed():
    result = run_cli("--focus", "definitely-missing-entity")
    assert result.returncode == 2
    payload = json.loads(result.stderr)
    assert payload["ok"] is False
    assert "could not be resolved" in payload["error"]


def test_fail_on_issues_uses_nonzero_review_exit_code(tmp_path):
    seed = {
        "schema_version": "agentos.relation-seed/v1",
        "mode": "shadow",
        "entities": [
            {"entity_id": "orphan", "kind": "project", "canonical_name": "Orphan"}
        ],
        "relations": []
    }
    path = tmp_path / "seed.json"
    path.write_text(json.dumps(seed), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(path), "--fail-on-issues"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 3
    payload = json.loads(result.stdout)
    assert payload["requires_work"] is True
    assert payload["issues"][0]["kind"] == "orphan_entity"
