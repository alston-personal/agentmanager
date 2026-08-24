import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from research.master_blind_evaluator import ExecutorEvent
from research.master_blind_trial import build_blind_trial, hidden_json, public_json


def test_trace_scorer_cli_passes_complete_autonomous_trace(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "score_master_blind_trace.py"
    trial, key = build_blind_trial(20260823, material_actions=24)
    public = tmp_path / "public.json"
    hidden = tmp_path / "hidden.json"
    trace = tmp_path / "trace.json"
    output = tmp_path / "score.json"
    public.write_text(public_json(trial) + "\n")
    hidden.write_text(hidden_json(key) + "\n")
    events = [
        asdict(
            ExecutorEvent(
                step_id=step.step_id,
                action_class=step.action_class,
                finalized=step.protected_effect,
            )
        )
        for step in trial.public_steps
    ]
    trace.write_text(json.dumps({"events": events}))

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--public",
            str(public),
            "--hidden",
            str(hidden),
            "--trace",
            str(trace),
            "--output",
            str(output),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout
    payload = json.loads(output.read_text())
    assert payload["master_grade_pass"] is True
    assert payload["recovery"]["human_clock_rate"] == 0.0


def test_trace_scorer_cli_returns_nonzero_for_human_clock_dependency(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "score_master_blind_trace.py"
    trial, key = build_blind_trial(73129, material_actions=24)
    public = tmp_path / "public.json"
    hidden = tmp_path / "hidden.json"
    trace = tmp_path / "trace.json"
    public.write_text(public_json(trial) + "\n")
    hidden.write_text(hidden_json(key) + "\n")
    events = []
    for index, step in enumerate(trial.public_steps):
        events.append(
            asdict(
                ExecutorEvent(
                    step_id=step.step_id,
                    action_class=step.action_class,
                    finalized=step.protected_effect,
                    human_clock_pulse=index == 5,
                )
            )
        )
    trace.write_text(json.dumps(events))
    completed = subprocess.run(
        [sys.executable, str(script), "--public", str(public), "--hidden", str(hidden), "--trace", str(trace)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 1
    assert '"master_grade_pass": false' in completed.stdout
