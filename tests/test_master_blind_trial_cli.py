import json
import subprocess
import sys
from pathlib import Path


def test_blind_trial_cli_works_from_arbitrary_cwd(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "build_master_blind_trial.py"
    public = tmp_path / "out" / "public.json"
    hidden = tmp_path / "secret" / "hidden.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--seed",
            "20260823",
            "--material-actions",
            "24",
            "--public-output",
            str(public),
            "--hidden-output",
            str(hidden),
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "trial_id=mbt-" in completed.stdout
    public_payload = json.loads(public.read_text())
    hidden_payload = json.loads(hidden.read_text())
    assert public_payload["trial_id"] == hidden_payload["trial_id"]
    assert len(public_payload["public_steps"]) == 24
    assert hidden_payload["minimum_material_actions"] == 23
    assert "expected_safe_order" not in public_payload
