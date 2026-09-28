#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import time
import shutil
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gradio_client import Client, handle_file

SCHEMA = "agentos.tryon-render-job/v1"
SPACE_ID = os.environ.get("AGENTOS_TRYON_SPACE_ID", "sm4ll-VTON/sm4ll-VTON-Demo")
DATA_ROOT = Path(os.environ.get("AGENT_DATA_ROOT", str(Path.home() / "agent-data"))).expanduser()
JOB_DIR = DATA_ROOT / "projects" / "dressup-simulator" / "render_jobs" / "runtime"
CURRENT_DIR = DATA_ROOT / "projects" / "dressup-simulator" / "current_outfits"
ASSET_DIR = DATA_ROOT / "projects" / "dressup-simulator" / "render_assets"
BASE_BODY_URL = os.environ.get(
    "AGENTOS_MIO_BASE_BODY_URL",
    "https://studio.milkcat.org/personas/mio/mio-avatar.webp",
)

SUPPORTED = {
    "upper_inner": "dress",
    "upper_main": "dress",
    "upper_outer": "dress",
    "onepiece": "dress",
    "shoes": "footwear",
}

ORDER = ["upper_inner", "upper_main", "onepiece", "upper_outer", "shoes"]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)


_CLIENT: Client | None = None


def client() -> Client:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = Client(
            SPACE_ID,
            download_files=True,
            verbose=False,
            httpx_kwargs={"timeout": 240.0},
        )
    return _CLIENT


def download_input(url: str, suffix: str) -> Path:
    req = urllib.request.Request(url, headers={"User-Agent": "AgentOS-Mio-TryOn/1.3"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        content_type = (resp.headers.get("Content-Type") or "").lower()
        if "image" not in content_type:
            raise RuntimeError(f"input is not image content: {content_type}")
        data = resp.read()
    if len(data) < 1000:
        raise RuntimeError("input image is unexpectedly small")
    fd, name = tempfile.mkstemp(prefix="mio-vton-", suffix=suffix)
    os.close(fd)
    path = Path(name)
    path.write_bytes(data)
    return path


def output_path(result: Any) -> Path:
    candidate: Any = result
    if isinstance(candidate, (list, tuple)) and candidate:
        candidate = candidate[0]
    if isinstance(candidate, dict):
        candidate = candidate.get("path") or candidate.get("url")
    if not isinstance(candidate, str) or not candidate:
        raise RuntimeError(f"SM4LL VTON returned no output path: {result!r}")
    path = Path(candidate)
    if not path.exists() or path.stat().st_size < 1000:
        raise RuntimeError(f"SM4LL VTON output missing or too small: {candidate}")
    return path


def sm4ll_try_on(person_source: str, garment_url: str, workflow: str) -> str:
    temp_inputs: list[Path] = []
    try:
        if person_source.startswith(("http://", "https://")):
            person_path = download_input(person_source, ".webp")
            temp_inputs.append(person_path)
        else:
            person_path = Path(person_source)
            if not person_path.exists():
                raise RuntimeError(f"person input missing: {person_source}")

        garment_path = download_input(garment_url, ".jpg")
        temp_inputs.append(garment_path)

        result = client().predict(
            handle_file(str(person_path)),
            handle_file(str(garment_path)),
            workflow,
            api_name="/generate",
        )
        return str(output_path(result))
    finally:
        for path in temp_inputs:
            try:
                path.unlink()
            except FileNotFoundError:
                pass


def copy_output(source: str, target: Path) -> None:
    path = Path(source)
    if not path.exists() or path.stat().st_size < 1000:
        raise RuntimeError("provider output image is missing or unexpectedly small")
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    shutil.copyfile(path, tmp)
    os.chmod(tmp, 0o600)
    tmp.replace(target)


def current_outfit_path(character_id: str) -> Path:
    return CURRENT_DIR / f"{character_id}.json"


def update_current(job: dict[str, Any]) -> None:
    path = current_outfit_path(str(job["characterId"]))
    current = read_json(path)
    if not current or current.get("tryOn", {}).get("jobId") != job.get("jobId"):
        return
    current["updatedAt"] = utc_now()
    current["tryOn"] = {
        "jobId": job["jobId"],
        "status": job["status"],
        "asset": job["output"].get("asset"),
        "previewAsset": job["output"].get("previewAsset"),
        "view": job.get("view", "front"),
    }
    atomic_write(path, current)


def public_asset_path(job_id: str) -> str:
    return f"/dashboard/api/wardrobe/tryon/assets/{job_id}"


def process_job(path: Path, job: dict[str, Any]) -> None:
    job["status"] = "rendering"
    job["startedAt"] = utc_now()
    job["error"] = None
    atomic_write(path, job)
    update_current(job)

    selected = job.get("input", {}).get("selectedLayers", {})
    if not isinstance(selected, dict):
        raise RuntimeError("selectedLayers missing")

    supported_layers = [layer for layer in ORDER if layer in selected and layer in SUPPORTED]
    if not supported_layers:
        raise RuntimeError("No renderable clothing layers selected yet")

    # Each pass uses the previous output as the new person image.
    person_url = BASE_BODY_URL
    provider_outputs: list[str] = []
    for layer in supported_layers:
        item = selected[layer]
        garment_url = item.get("sourceImageUrl") if isinstance(item, dict) else None
        if not isinstance(garment_url, str) or not garment_url.startswith(("http://", "https://")):
            raise RuntimeError(f"Missing source image for {layer}")
        person_url = sm4ll_try_on(person_url, garment_url, SUPPORTED[layer])
        provider_outputs.append(person_url)

    target = ASSET_DIR / f"{job['jobId']}.webp"
    copy_output(person_url, target)

    job["status"] = "ready"
    job["completedAt"] = utc_now()
    job["failedAt"] = None
    job["output"] = {
        "asset": public_asset_path(job["jobId"]),
        "previewAsset": public_asset_path(job["jobId"]),
        "width": None,
        "height": None,
        "provider": "sm4ll-vton-gradio-client",
        "providerSpace": SPACE_ID,
        "providerOutputs": provider_outputs,
        "renderedLayers": supported_layers,
    }
    atomic_write(path, job)
    update_current(job)


def mark_failed(path: Path, job: dict[str, Any], exc: Exception) -> None:
    job["status"] = "failed"
    job["failedAt"] = utc_now()
    job["error"] = {
        "code": "renderer_failed",
        "message": f"{type(exc).__name__}: {exc}"[:1000],
    }
    atomic_write(path, job)
    update_current(job)


def next_job() -> tuple[Path, dict[str, Any]] | None:
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    candidates: list[tuple[str, Path, dict[str, Any]]] = []
    for path in JOB_DIR.glob("*.json"):
        job = read_json(path)
        if not job or job.get("schema") != SCHEMA or job.get("status") != "queued":
            continue
        candidates.append((str(job.get("requestedAt") or ""), path, job))
    if not candidates:
        return None
    _, path, job = sorted(candidates, key=lambda row: row[0])[0]
    return path, job


def main() -> int:
    interval = float(os.environ.get("AGENTOS_TRYON_POLL_SECONDS", "2"))
    once = os.environ.get("AGENTOS_TRYON_ONCE") == "1"
    while True:
        found = next_job()
        if found is None:
            if once:
                return 0
            time.sleep(interval)
            continue
        path, job = found
        try:
            process_job(path, job)
        except Exception as exc:
            mark_failed(path, job, exc)
        if once:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
