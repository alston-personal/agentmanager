#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "agentos.tryon-render-job/v1"
SPACE_BASE = os.environ.get("AGENTOS_TRYON_SPACE_BASE", "https://fashn-ai-fashn-vton-1-5.hf.space")
DATA_ROOT = Path(os.environ.get("AGENT_DATA_ROOT", str(Path.home() / "agent-data"))).expanduser()
JOB_DIR = DATA_ROOT / "projects" / "dressup-simulator" / "render_jobs" / "runtime"
CURRENT_DIR = DATA_ROOT / "projects" / "dressup-simulator" / "current_outfits"
ASSET_DIR = DATA_ROOT / "projects" / "dressup-simulator" / "render_assets"
BASE_BODY_URL = os.environ.get(
    "AGENTOS_MIO_BASE_BODY_URL",
    "https://studio.milkcat.org/personas/mio/mio-avatar.webp",
)

SUPPORTED = {
    "upper_inner": "tops",
    "upper_main": "tops",
    "upper_outer": "tops",
    "lower_main": "bottoms",
    "onepiece": "one-pieces",
}

ORDER = ["upper_inner", "upper_main", "lower_main", "onepiece", "upper_outer"]


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


def http_json(url: str, payload: dict[str, Any], timeout: int = 180) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:4000]
        raise RuntimeError(f"HTTP {exc.code} from VTON provider: {detail}") from exc
    value = json.loads(body.decode("utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("VTON provider returned non-object JSON")
    return value

def gradio_queue_call(api_name: str, data_values: list[Any], timeout: int = 300) -> Any:
    queued = http_json(
        f"{SPACE_BASE}/gradio_api/call/{api_name}",
        {"data": data_values},
        timeout=30,
    )
    event_id = queued.get("event_id")
    if not isinstance(event_id, str) or not event_id:
        raise RuntimeError(f"Gradio queue returned no event_id: {queued}")

    url = f"{SPACE_BASE}/gradio_api/call/{api_name}/{event_id}"
    req = urllib.request.Request(url, headers={"Accept": "text/event-stream"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            event = None
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                if line.startswith("event:"):
                    event = line.split(":", 1)[1].strip()
                    continue
                if not line.startswith("data:"):
                    continue
                payload = line.split(":", 1)[1].strip()
                if event == "error":
                    raise RuntimeError(f"Gradio queue error: {payload[:2000]}")
                if event == "complete":
                    value = json.loads(payload)
                    return value
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:4000]
        raise RuntimeError(f"HTTP {exc.code} from Gradio queue: {detail}") from exc
    raise RuntimeError("Gradio queue closed without complete event")



def download(url: str, target: Path, timeout: int = 60) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "AgentOS-Mio-TryOn/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        content_type = (resp.headers.get("Content-Type") or "").lower()
        if "image" not in content_type:
            raise RuntimeError(f"provider output is not image content: {content_type}")
        data = resp.read()
    if len(data) < 1000:
        raise RuntimeError("provider output image is unexpectedly small")
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_bytes(data)
    os.chmod(tmp, 0o600)
    tmp.replace(target)


def image_data(url: str) -> dict[str, Any]:
    return {
        "path": url,
        "url": url,
        "orig_name": url.rsplit("/", 1)[-1].split("?", 1)[0] or "image",
        "meta": {"_type": "gradio.FileData"},
    }


def try_on(person_url: str, garment_url: str, category: str, seed: int) -> str:
    result = gradio_queue_call(
        "try_on",
        [
            image_data(person_url),
            image_data(garment_url),
            category,
            "model",
            30,
            1.5,
            seed,
            True,
        ],
        timeout=300,
    )
    out = result[0] if isinstance(result, list) and result and isinstance(result[0], dict) else None
    if not isinstance(out, dict):
        raise RuntimeError(f"VTON provider returned no output object: {result}")
    url = out.get("url")
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        raise RuntimeError("VTON provider returned no output URL")
    return url


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

    # Each pass uses the previous output as the new person image. This gives a
    # practical MVP for tops/bottoms while preserving the same Mio base body.
    person_url = BASE_BODY_URL
    seed_base = abs(hash(job["jobId"])) % 100000
    provider_urls: list[str] = []
    for index, layer in enumerate(supported_layers):
        item = selected[layer]
        garment_url = item.get("sourceImageUrl") if isinstance(item, dict) else None
        if not isinstance(garment_url, str) or not garment_url.startswith(("http://", "https://")):
            raise RuntimeError(f"Missing source image for {layer}")
        person_url = try_on(person_url, garment_url, SUPPORTED[layer], seed_base + index)
        provider_urls.append(person_url)

    target = ASSET_DIR / f"{job['jobId']}.png"
    download(person_url, target)

    job["status"] = "ready"
    job["completedAt"] = utc_now()
    job["failedAt"] = None
    job["output"] = {
        "asset": public_asset_path(job["jobId"]),
        "previewAsset": public_asset_path(job["jobId"]),
        "width": 576,
        "height": 864,
        "provider": "fashn-vton-1.5-hf-space",
        "providerUrls": provider_urls,
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
