import json
from pathlib import Path
import subprocess
import sys

from agent_core.cognitive_observatory import CognitiveObservatory
from agent_core.cognitive_observatory_store import CognitiveObservatoryStore


def seed_db(path: Path):
    store = CognitiveObservatoryStore(path)
    first = CognitiveObservatory.snapshot(
        project_id="agentmanager",
        captured_at="2026-08-21T00:00:00Z",
        trigger_ref="review:0",
    )
    second = CognitiveObservatory.snapshot(
        project_id="agentmanager",
        captured_at="2026-08-22T00:00:00Z",
        trigger_ref="review:1",
    )
    store.persist_snapshot(first)
    store.persist_snapshot(second)
    store.persist_delta(CognitiveObservatory.diff(first, second, annotations=("rereview",)))


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "scripts/export_cognitive_observatory.py", *args],
        text=True,
        capture_output=True,
        check=False,
    )


def test_cli_exports_json_to_stdout(tmp_path):
    db = tmp_path / "cognition.sqlite3"
    seed_db(db)
    result = run_cli("--db", str(db), "--project", "agentmanager", "--format", "json")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert len(payload["timeline"]) == 2
    assert payload["deltas"][0]["payload"]["annotations"] == ["rereview"]


def test_cli_exports_dot_to_file(tmp_path):
    db = tmp_path / "cognition.sqlite3"
    seed_db(db)
    output = tmp_path / "timeline.dot"
    result = run_cli(
        "--db", str(db),
        "--project", "agentmanager",
        "--format", "dot",
        "--output", str(output),
        "--title", "AgentOS evolution",
    )
    assert result.returncode == 0
    content = output.read_text(encoding="utf-8")
    assert "digraph cognition_timeline" in content
    assert "AgentOS evolution" in content
    assert "rereview" in content


def test_cli_missing_database_fails_without_creating_it(tmp_path):
    missing = tmp_path / "missing.sqlite3"
    result = run_cli("--db", str(missing), "--project", "agentmanager")
    assert result.returncode == 2
    assert "not found" in result.stderr
    assert not missing.exists()
