#!/usr/bin/env python3
"""Run one fixed Character Blueprint benchmark case through Meshy Image-to-3D.

The script deliberately stores raw provider evidence and emits the same result schema
used by the local Character Blueprint baseline. It never prints the API key.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = "https://api.meshy.ai"
CREATE_PATH = "/openapi/v1/image-to-3d"
TERMINAL = {"SUCCEEDED", "FAILED", "CANCELED"}


def request_json(method: str, url: str, key: str, payload: dict | None = None, timeout: int = 90) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Meshy HTTP {exc.code}: {body[:1200]}") from exc
    except URLError as exc:
        raise RuntimeError(f"Meshy network error: {exc}") from exc


def download(url: str, path: Path, timeout: int = 180) -> None:
    req = Request(url, headers={"User-Agent": "CharacterBlueprintBenchmark/0.1"})
    with urlopen(req, timeout=timeout) as resp:
        path.write_bytes(resp.read())
    if path.stat().st_size <= 0:
        raise RuntimeError(f"empty download: {path}")


def image_data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    if mime not in {"image/jpeg", "image/png"}:
        raise SystemExit(f"Meshy fixture must be jpg/jpeg/png, got {mime}")
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--case-id", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ai-model", default="meshy-7")
    ap.add_argument("--poll-seconds", type=float, default=5.0)
    ap.add_argument("--timeout-seconds", type=int, default=1800)
    args = ap.parse_args()

    key = os.environ.get("MESHY_API_KEY", "").strip()
    if not key:
        raise SystemExit("MESHY_API_KEY is required")

    image = Path(args.image)
    if not image.is_file():
        raise SystemExit(f"fixture not found: {image}")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    source = image.read_bytes()
    source_sha = hashlib.sha256(source).hexdigest()
    (out / f"source{image.suffix.lower() or '.jpg'}").write_bytes(source)

    settings = {
        "model_type": "standard",
        "ai_model": args.ai_model,
        "image_enhancement": False,
        "should_texture": False,
        "enable_pbr": False,
        "should_remesh": False,
        "target_formats": ["glb"],
        "auto_size": True,
        "origin_at": "bottom",
        "multi_view_thumbnails": True,
        "pose_mode": "",
    }
    payload = {"image_url": image_data_uri(image), **settings}

    started_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    t0 = time.monotonic()
    created = request_json("POST", BASE_URL + CREATE_PATH, key, payload)
    task_id = created.get("result")
    if not task_id:
        raise RuntimeError(f"Meshy create response missing task id: {created}")

    deadline = time.monotonic() + args.timeout_seconds
    task = None
    while time.monotonic() < deadline:
        task = request_json("GET", f"{BASE_URL}{CREATE_PATH}/{task_id}", key)
        status = str(task.get("status") or "")
        progress = task.get("progress")
        print(f"meshy_task={task_id} status={status} progress={progress}", flush=True)
        if status in TERMINAL:
            break
        time.sleep(args.poll_seconds)
    else:
        raise RuntimeError(f"Meshy task timed out after {args.timeout_seconds}s: {task_id}")

    assert task is not None
    (out / "provider-response.json").write_text(json.dumps(task, indent=2) + "\n", encoding="utf-8")
    if task.get("status") != "SUCCEEDED":
        raise RuntimeError(f"Meshy task {task.get('status')}: {(task.get('task_error') or {}).get('message', 'unknown error')}")

    glb_url = (task.get("model_urls") or {}).get("glb")
    if not glb_url:
        raise RuntimeError("Meshy succeeded without model_urls.glb")
    download(glb_url, out / "model.glb")

    thumbnails = task.get("thumbnail_urls") or {}
    saved_views: dict[str, str | None] = {"front": None, "yaw45": None, "right": None, "back": None}
    for view in ("front", "right", "back", "left"):
        url = thumbnails.get(view)
        if url:
            name = f"provider-{view}.png"
            download(url, out / name)
            if view in saved_views:
                saved_views[view] = name

    duration = time.monotonic() - t0
    result = {
        "schema": "character-blueprint-benchmark-result/v0.1",
        "case_id": args.case_id,
        "system_id": "meshy",
        "model_version": args.ai_model,
        "settings": settings,
        "source_sha256": source_sha,
        "started_at": started_iso,
        "duration_seconds": round(duration, 3),
        "credits": task.get("consumed_credits"),
        "estimated_cost_usd": None,
        "model_path": "model.glb",
        "renders": saved_views,
        "geometry": {"vertices": None, "faces": None, "components": None},
        "scores": {},
        "evidence": {
            "provider_response": "provider-response.json",
            "provider_task_id": task_id,
            "provider_progress": task.get("progress"),
            "provider_thumbnail_left": "provider-left.png" if (out / "provider-left.png").exists() else None,
        },
        "notes": [
            "Meshy geometry baseline: texture disabled and image enhancement disabled.",
            "Provider cardinal thumbnails are retained as evidence; yaw45 is filled by the canonical GLB renderer in a later step.",
            "Signed provider URLs in provider-response.json may expire; downloaded evidence is authoritative.",
        ],
    }
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "provider": "meshy", "task_id": task_id, "out": str(out), "credits": task.get("consumed_credits")}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"character_blueprint_meshy_benchmark=FAIL {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
