import json
from pathlib import Path
import subprocess
import sys

from research.lccb_synthetic import generate_pack, private_labels_jsonl


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "scripts/score_lccb_responses.py", *args],
        text=True,
        capture_output=True,
        check=False,
    )


def test_scoring_cli_scores_complete_stage(tmp_path):
    pack = generate_pack()
    root = tmp_path / "pack"
    (root / "private").mkdir(parents=True)
    (root / "private" / "labels.jsonl").write_text(private_labels_jsonl(pack), encoding="utf-8")

    labels = [item for item in pack.labels if item.stage == 0]
    responses = tmp_path / "responses.jsonl"
    responses.write_text(
        "\n".join(
            json.dumps(
                {
                    "model": "demo-model",
                    "repeat": 0,
                    "stage": 0,
                    "task_key": item.task_key,
                    "response_text": "unknown",
                }
            )
            for item in labels
        ) + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "scores.json"
    result = run_cli("--pack", str(root), "--responses", str(responses), "--output", str(output))
    assert result.returncode == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["results"][0]["metrics"]["fact_recall_accuracy"] == 1.0


def test_scoring_cli_fails_closed_on_missing_task(tmp_path):
    pack = generate_pack()
    root = tmp_path / "pack"
    (root / "private").mkdir(parents=True)
    (root / "private" / "labels.jsonl").write_text(private_labels_jsonl(pack), encoding="utf-8")
    labels = [item for item in pack.labels if item.stage == 0][1:]
    responses = tmp_path / "responses.jsonl"
    responses.write_text(
        "\n".join(json.dumps({"model": "demo", "repeat": 0, "stage": 0, "task_key": item.task_key, "response_text": "unknown"}) for item in labels) + "\n",
        encoding="utf-8",
    )
    result = run_cli("--pack", str(root), "--responses", str(responses), "--output", str(tmp_path / "scores.json"))
    assert result.returncode == 2
    assert "missing responses" in result.stderr
