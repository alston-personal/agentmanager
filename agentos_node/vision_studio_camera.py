"""Versioned, provider-neutral camera motion IR compiler for Vision Studio.

No model-specific motion success is implied by prompt compilation.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

MOTIONS = {
    "locked": "Keep the physical camera stationary",
    "dolly": "Physically move the camera",
    "pan": "Rotate the camera horizontally",
    "tilt": "Rotate the camera vertically",
    "orbit": "Move the camera around the subject",
    "zoom": "Change optical focal length without moving the camera",
    "crane": "Move the camera vertically",
    "handheld_stable": "Use restrained, stable handheld camera movement",
}
DIRECTIONS = {"none": "", "forward": "forward", "backward": "backward", "left": "left", "right": "right",
              "up": "up", "down": "down", "clockwise": "clockwise", "counterclockwise": "counterclockwise"}
SPEEDS = {"still": "", "subtle": "very subtly", "slow": "slowly", "moderate": "at a moderate speed", "fast": "rapidly"}
FRAMINGS = {"wide", "medium", "close_up", "rear_wide", "medium_close_up", "extreme_close_up"}


def render_camera_motion(motion: dict[str, Any]) -> str:
    if not isinstance(motion, dict) or motion.get("version") != 1:
        raise ValueError("camera_motion_version_unsupported")
    kind = motion.get("type")
    if kind not in MOTIONS:
        raise ValueError("camera_motion_type_unsupported")
    direction = motion.get("direction", "none")
    speed = motion.get("speed", "moderate")
    if direction not in DIRECTIONS or speed not in SPEEDS:
        raise ValueError("camera_motion_direction_or_speed_unsupported")
    if kind == "locked" and (direction != "none" or speed != "still"):
        raise ValueError("locked_camera_must_be_stationary")
    if kind == "handheld_stable" and direction != "none":
        raise ValueError("handheld_direction_unsupported")
    start, end = motion.get("start_framing"), motion.get("end_framing")
    if start not in FRAMINGS or end not in FRAMINGS:
        raise ValueError("camera_motion_framing_unsupported")
    if type(motion.get("subject_lock")) is not bool:
        raise ValueError("camera_motion_subject_lock_required")
    fragment = MOTIONS[kind]
    attributes = [SPEEDS[speed], DIRECTIONS[direction]]
    if any(attributes):
        fragment += " " + " ".join(v for v in attributes if v)
    fragment += f"; frame starts {start.replace('_', ' ')} and ends {end.replace('_', ' ')}"
    fragment += "; keep the subject centered in frame" if motion["subject_lock"] else "; allow the subject to move across frame"
    return "Camera direction: " + fragment + "."


def compile_shots(manifest: dict[str, Any]) -> list[tuple[str, str]]:
    shots = manifest.get("shots") if isinstance(manifest, dict) else None
    if not isinstance(shots, list) or not shots:
        raise ValueError("vision_studio_shots_missing")
    results = []
    seen = set()
    for shot in shots:
        if not isinstance(shot, dict) or not isinstance(shot.get("id"), str):
            raise ValueError("vision_studio_shot_id_invalid")
        shot_id = shot["id"]
        if shot_id in seen:
            raise ValueError("vision_studio_duplicate_shot")
        seen.add(shot_id)
        motion = shot.get("camera_motion")
        if motion is None:
            legacy = shot.get("camera")
            if not isinstance(legacy, str) or not legacy.strip() or "\n" in legacy:
                raise ValueError("vision_studio_legacy_camera_invalid")
            fragment = "Camera direction: " + legacy.strip() + "."
        else:
            fragment = render_camera_motion(motion)
        if "\n" in fragment or "\r" in fragment:
            raise ValueError("vision_studio_camera_multiline")
        results.append((shot_id, fragment))
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    manifest = yaml.safe_load(args.manifest.read_text(encoding="utf-8"))
    for shot_id, line in compile_shots(manifest):
        print(f"{shot_id}\t{line}")


if __name__ == "__main__":
    main()
