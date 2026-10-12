#!/usr/bin/env bash
set -euo pipefail

ACTIVE_SLOT="$(cat /home/ubuntu/agent-data/runtime/dashboard-blue-green/active-slot)"
RELEASE="$(readlink -f "/home/ubuntu/agent-data/runtime/dashboard/$ACTIVE_SLOT")"
test -f "$RELEASE/scripts/character_fusion_worker.py"
test -f "$RELEASE/libs/model2ir/src/model2ir/reconciliation.py"

SOURCE=/tmp/character-fusion-live-smoke.webp
OUTPUT=/tmp/character-fusion-live-smoke.png
trap 'rm -f "$SOURCE" "$OUTPUT"' EXIT

curl -fL --retry 3 --max-time 30 \
  https://studio.milkcat.org/personas/mio/mio-base-v2.webp \
  -o "$SOURCE"
test -s "$SOURCE"

AGENTOS_REPO_ROOT="$RELEASE" python3 - "$SOURCE" "$OUTPUT" <<'PY'
import importlib.util
import json
import os
import sys
from pathlib import Path

source=Path(sys.argv[1])
output=Path(sys.argv[2])
release=Path(os.environ["AGENTOS_REPO_ROOT"])
worker_path=release/"scripts"/"character_fusion_worker.py"
spec=importlib.util.spec_from_file_location("character_fusion_live_worker",worker_path)
if spec is None or spec.loader is None:
    raise SystemExit("worker import failed")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

person_ir=mod.extract_person_traits(source)
target=mod.fuse(mod.water_drop_main_ir(),person_ir)
image=mod.render_image(target,source,None,strict=True)
output.write_bytes(image)
actual=mod.inspect_output(output)
acceptance=mod.accept("water-drop",target,actual)
print(json.dumps({
    "person_traits": person_ir,
    "target_body_plan": target.get("body_plan"),
    "actual": actual,
    "smoke_acceptance": acceptance,
    "image_bytes": len(image),
    "image_model": mod.IMAGE_MODEL,
    "vision_model": mod.VISION_MODEL,
},ensure_ascii=False))
if len(image) < 10000:
    raise SystemExit("generated image unexpectedly small")
if not acceptance.get("pass"):
    raise SystemExit("character fusion live acceptance failed")
PY

echo 'character_fusion_live_smoke=PASS'
