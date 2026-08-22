import json
from pathlib import Path
import subprocess
import sys


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "scripts/build_lccb_synthetic_pack.py", *args],
        text=True,
        capture_output=True,
        check=False,
    )


def test_cli_builds_separate_public_private_artifacts_and_manifest(tmp_path):
    output = tmp_path / "pack"
    result = run_cli("--output-dir", str(output), "--seed", "73129", "--events", "1000")
    assert result.returncode == 0

    experience_path = output / "public" / "experience.jsonl"
    tasks_path = output / "public" / "tasks.jsonl"
    private_path = output / "private" / "labels.jsonl"
    manifest_path = output / "manifest.json"
    assert experience_path.exists() and tasks_path.exists() and private_path.exists() and manifest_path.exists()

    experience_text = experience_path.read_text(encoding="utf-8")
    tasks_text = tasks_path.read_text(encoding="utf-8")
    private_text = private_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for public_text in (experience_text, tasks_text):
        assert '"expected_facts"' not in public_text
        assert '"forbidden_facts"' not in public_text
        assert '"evidence_source_refs"' not in public_text
    assert '"prompt"' in tasks_text
    assert '"expected_facts"' in private_text
    assert manifest["event_count"] == 1000
    assert manifest["task_count_by_stage"]["0"] == manifest["task_count_by_stage"]["100"] == manifest["task_count_by_stage"]["1000"]
    assert manifest["public_experience_artifact"] == "public/experience.jsonl"
    assert manifest["public_tasks_artifact"] == "public/tasks.jsonl"
    assert manifest["private_artifact_must_not_be_exposed_to_agent"] is True
    assert len(manifest["experience_manifest_hash"]) == 64
    assert len(manifest["evaluator_manifest_hash"]) == 64


def test_same_seed_produces_same_frozen_manifest_hashes(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    assert run_cli("--output-dir", str(first)).returncode == 0
    assert run_cli("--output-dir", str(second)).returncode == 0
    a = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
    b = json.loads((second / "manifest.json").read_text(encoding="utf-8"))
    assert a["experience_manifest_hash"] == b["experience_manifest_hash"]
    assert a["evaluator_manifest_hash"] == b["evaluator_manifest_hash"]


def test_cli_rejects_too_short_pack(tmp_path):
    output = tmp_path / "bad"
    result = run_cli("--output-dir", str(output), "--events", "99")
    assert result.returncode == 2
    assert "at least 100" in result.stderr
    assert not output.exists()
