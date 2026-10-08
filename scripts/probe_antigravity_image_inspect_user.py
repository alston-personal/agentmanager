#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

REPO = Path("/home/ubuntu/agentmanager")
RUNTIME_LIB = Path("/home/ubuntu/.local/share/mio-tryon/runtime-lib")
for entry in (REPO, RUNTIME_LIB):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from agentos_node.antigravity_relay import AntigravityRelayClient
from capabilities.wardrobe_visual_review.gemini_backend import _download


def latest_candidate():
    root = Path("/home/ubuntu/agent-data/projects/dressup-simulator")
    rows = []
    for path in (root / "render_jobs/runtime").glob("*.json"):
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        asset = root / "render_assets" / f"{job.get('jobId')}.webp"
        selected = ((job.get("input") or {}).get("selectedLayers") or {})
        if job.get("status") == "ready" and asset.is_file() and selected:
            rows.append((job.get("completedAt") or job.get("requestedAt") or "", job, asset))
    return sorted(rows, reverse=True)[0] if rows else None


def main() -> int:
    found = latest_candidate()
    if found is None:
        print("antigravity_image_inspect_probe=SKIP_NO_CANDIDATE")
        return 0

    _, job, asset = found
    work = Path("/home/ubuntu/agent-data/runtime/agy-image-probe")
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    shutil.copy2(asset, work / "candidate.webp")

    layer, item = next(iter(((job.get("input") or {}).get("selectedLayers") or {}).items()))
    source = str((item or {}).get("sourceImageUrl") or "")
    if not source.startswith(("http://", "https://")):
        print("antigravity_image_inspect_probe=INVALID_REFERENCE")
        return 0
    _download(source, work / "reference.jpg")

    client = AntigravityRelayClient("/home/ubuntu/agent-data/runtime/antigravity-relay")
    instruction = (
        "Read candidate.webp and reference.jpg as images. Do not modify any file. "
        f"Determine whether the generated candidate visibly contains an item matching the reference image for wardrobe layer {layer}. "
        'Return exactly one JSON object and nothing else: '
        '{"schema":"agentos.image-inspect-probe/v1","imageReadable":true,'
        f'"layer":"{layer}","match":true_or_false,"evidence":"brief visual evidence"}} '
        "If you cannot actually inspect the image pixels, return imageReadable=false."
    )
    capsule = client.submit(
        project_id="agentos-core",
        canonical_ir={
            "schema": "agentos.executor-provider-ir/v0.1",
            "goal": "Probe Antigravity image inspection only",
            "operation": "agent.chat",
            "constraints": [
                "read-only",
                "no file mutation",
                "no credentials",
                "return structured JSON",
            ],
        },
        instruction=instruction,
        workspace=str(work),
        executor_hint="provider:agy",
    )
    capsule_id = capsule["capsule_id"]
    print("antigravity_image_probe_capsule=" + capsule_id)

    for _ in range(60):
        receipt = client.receipt(capsule_id)
        if receipt:
            print("antigravity_image_probe_provider=" + str(receipt.get("provider")))
            print("antigravity_image_probe_ok=" + str(receipt.get("ok")))
            output = str(receipt.get("stdout") or "").replace("\n", " ")[:3000]
            print("antigravity_image_probe_output=" + output)
            if receipt.get("ok") is not True:
                print("antigravity_image_inspect_probe=BACKEND_ERROR")
                return 0
            compact = output.lower().replace(" ", "")
            if '"imagereadable":true' in compact:
                print("antigravity_image_inspect_probe=READY")
            else:
                print("antigravity_image_inspect_probe=UNSUPPORTED")
            return 0
        time.sleep(2)

    print("antigravity_image_inspect_probe=TIMEOUT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
