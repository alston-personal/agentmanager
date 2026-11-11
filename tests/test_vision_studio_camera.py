from pathlib import Path

import pytest
import yaml

from agentos_node.vision_studio_camera import compile_shots, render_camera_motion

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "examples/vision-studio/rain-exit-v001.yaml"


def test_existing_rain_exit_manifest_compiles_all_four_shots():
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    shots = compile_shots(manifest)
    assert [shot_id for shot_id, _ in shots] == ["s01", "s02", "s03", "s04"]
    assert "forward" in shots[0][1]
    assert "backward" in shots[1][1]
    assert "handheld" in shots[2][1]
    assert "stationary" in shots[3][1]
    assert all("\n" not in prompt and "\t" not in prompt for _, prompt in shots)


def test_legacy_camera_string_compiles_without_schema_migration():
    assert compile_shots({"shots": [{"id": "s01", "camera": "slow dolly backward"}]}) == [
        ("s01", "Camera direction: slow dolly backward.")
    ]


@pytest.mark.parametrize("changes,reason", [
    ({"version": 2}, "version"),
    ({"type": "teleport"}, "type"),
    ({"speed": "impossibly_fast"}, "direction_or_speed"),
    ({"direction": "outside"}, "direction_or_speed"),
    ({"subject_lock": "true"}, "subject_lock"),
    ({"start_framing": "nonsense"}, "framing"),
])
def test_camera_ir_fails_closed_on_unsupported_values(changes, reason):
    motion = {
        "version": 1,
        "type": "dolly",
        "direction": "forward",
        "speed": "slow",
        "start_framing": "wide",
        "end_framing": "medium",
        "subject_lock": True,
    }
    motion.update(changes)
    with pytest.raises(ValueError, match=reason):
        render_camera_motion(motion)


def test_locked_camera_cannot_move():
    with pytest.raises(ValueError, match="stationary"):
        render_camera_motion({
            "version": 1, "type": "locked", "direction": "forward",
            "speed": "slow", "start_framing": "wide",
            "end_framing": "wide", "subject_lock": True,
        })


def test_duplicate_shot_ids_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        compile_shots({"shots": [{"id": "s01", "camera": "locked"},
                                 {"id": "s01", "camera": "locked"}]})


def test_producer_reads_same_pinned_ir_and_generator_source():
    source = (ROOT / "scripts/produce_vision_studio_user.sh").read_text(encoding="utf-8")
    assert '$SOURCE_COMMIT:agentos_node/vision_studio_camera.py' in source
    assert '$SOURCE_COMMIT:examples/vision-studio/rain-exit-v001.yaml' in source
    assert '$SOURCE_COMMIT:scripts/generate_google_flow_user.sh' in source
    assert 'PROMPT[$i]+=" $camera_direction"' in source
    assert '"compiled_instructions_sha256": camera_ir_sha256' in source
    assert '"source_commit": source_commit' in source
    assert "CAMERA_IR_SHOT_COUNT_MISMATCH" in source
