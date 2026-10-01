import json
import subprocess
import sys
import tempfile
from pathlib import Path


def test_persona_pdca_tick_accepts_null_advisory_cadence():
    repo = Path(__file__).resolve().parents[1]
    script = repo / "scripts" / "persona_pdca_tick.py"
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "pdca").mkdir(parents=True)
        (root / "events").mkdir(parents=True)
        (root / "persona_state.json").write_text(json.dumps({
            "energy": {"capacity": 100, "current": 72, "recovery": {
                "awake_points_per_hour": 3,
                "rest_points_per_hour": 7,
                "sleep_points_per_hour": 12
            }, "action_costs": {"observe_passive": 0.2, "read_thread": 1}},
        }), encoding="utf-8")
        (root / "ir" ).mkdir(parents=True)
        (root / "ir" / "current.json").write_text(json.dumps({
            "ir_id": "test-ir"
        }), encoding="utf-8")
        (root / "pdca" / "config.json").write_text(json.dumps({
            "enabled": True,
            "persona_id": "test-persona",
            "timezone": "Asia/Taipei",
            "growth_mode": {
                "enabled": True,
                "phase": "reach_first",
                "daily_post_target": None,
                "daily_post_max": None,
                "minimum_post_gap_minutes": None
            }
        }), encoding="utf-8")
        (root / "pdca" / "state.json").write_text(json.dumps({
            "schema": "agentos.persona-pdca-state/v1",
            "cycle": 0,
            "status": "RUNNING",
            "energy_current": 72,
            "pending_external_actions": [],
            "consecutive_noops": 0
        }), encoding="utf-8")
        (root / "events" / "events.jsonl").write_text("", encoding="utf-8")
        receipt = root / "receipt.json"
        run = subprocess.run(
            [sys.executable, str(script), "--persona-dir", str(root), "--receipt-out", str(receipt), "--trigger", "test"],
            text=True,
            capture_output=True,
        )
        assert run.returncode == 0, run.stderr + run.stdout
        data = json.loads(receipt.read_text(encoding="utf-8"))
        assert data["cycle"] == 1
        assert data["plan"]["growth"]["target"] == 1
        assert data["plan"]["growth"]["max"] == 2
