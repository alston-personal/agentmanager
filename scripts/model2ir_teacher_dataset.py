#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from model2ir import TeacherDatasetError, build_teacher_dataset
from model2ir.teacher import sha256_file


def dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def node_renderer(renderer: str):
    """Adapt the repository's Playwright/Three.js renderer to model2ir's renderer API."""

    def render(local_asset: Path, case_dir: Path):
        result_stub = case_dir / "render-result.json"
        dump(
            result_stub,
            {
                "case_id": case_dir.name,
                "source_sha256": sha256_file(local_asset),
            },
        )
        subprocess.run(
            [
                "node",
                renderer,
                "--glb",
                str(local_asset),
                "--out",
                str(case_dir),
                "--result",
                str(result_stub),
            ],
            check=True,
        )
        result = json.loads(result_stub.read_text(encoding="utf-8"))
        renders = result.get("renders")
        if not isinstance(renders, dict):
            raise TeacherDatasetError("renderer did not return canonical render paths")
        return renders

    return render


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--asset", required=True)
    ap.add_argument("--case-id", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--renderer", default="scripts/character_blueprint_glb_render.mjs")
    args = ap.parse_args()

    try:
        manifest = build_teacher_dataset(
            args.asset,
            args.case_id,
            args.out,
            renderer=node_renderer(args.renderer),
        )
    except TeacherDatasetError as exc:
        raise SystemExit(str(exc)) from exc

    case = manifest["cases"][0]
    print(
        json.dumps(
            {
                "ok": True,
                "case_id": case["case_id"],
                "stability": case["stability"],
                "examples": len(manifest["examples"]),
                "target_ir_digest": case["target_ir_digest"],
            }
        )
    )


if __name__ == "__main__":
    main()
