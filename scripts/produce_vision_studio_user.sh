#!/usr/bin/env bash
set -euo pipefail

EXEC_USER="$(id -un)"
if [[ "$EXEC_USER" != "ubuntu" ]]; then
  echo "vision_studio_produce=WRONG_USER"
  echo "vision_studio_executor_user=$EXEC_USER"
  exit 2
fi

PROJECT_ID="${AGENTOS_VISION_STUDIO_PROJECT_ID:-}"
if [[ ! "$PROJECT_ID" =~ ^[a-z0-9][a-z0-9-]{0,63}$ ]]; then
  echo "vision_studio_produce=INVALID_PROJECT_ID"
  exit 3
fi
if [[ "$PROJECT_ID" != "rain-exit-v001" ]]; then
  echo "vision_studio_produce=PROJECT_NOT_ALLOWLISTED"
  exit 4
fi

REPO="${AGENTOS_REPO:-/home/ubuntu/agentmanager}"
SOURCE_COMMIT="${AGENTOS_SOURCE_COMMIT:-}"
FFMPEG="$(command -v ffmpeg || true)"
if [[ -z "$SOURCE_COMMIT" || ! "$SOURCE_COMMIT" =~ ^[0-9a-f]{40}$ ]]; then
  echo "vision_studio_produce=SOURCE_COMMIT_MISSING"
  exit 5
fi
FLOW_TMP="$(mktemp /tmp/agentos-vision-flow-XXXXXX.sh)"
cleanup() { rm -f "$FLOW_TMP"; }
trap cleanup EXIT
if ! git -C "$REPO" show "$SOURCE_COMMIT:scripts/generate_google_flow_user.sh" > "$FLOW_TMP"; then
  echo "vision_studio_produce=FLOW_GENERATOR_MATERIALIZE_FAILED"
  exit 5
fi
chmod 0700 "$FLOW_TMP"
FLOW="$FLOW_TMP"
if [[ -z "$FFMPEG" ]]; then
  echo "vision_studio_produce=FFMPEG_MISSING"
  exit 6
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_ROOT="/home/ubuntu/agent-data/artifacts/vision-studio/$PROJECT_ID/$STAMP-$$"
mkdir -p "$RUN_ROOT"
chmod 0755 "$RUN_ROOT"

declare -a DUR=(2 3 2 3)
declare -a SHOT=(s01 s02 s03 s04)
declare -a PROMPT
PROMPT[0]='Vertical 9:16 cinematic 35mm film. Same young East Asian woman, Mio, canonical consistent face and outfit, holding a transparent umbrella, walks up a Taipei metro exit staircase into light rain at night. Wide shot, restrained neon reflections on wet pavement, subtle slow push, natural anatomy and walking motion, realistic Taipei urban atmosphere, no text, no subtitles.'
PROMPT[1]='Vertical 9:16 cinematic 35mm film. Same young East Asian woman, Mio, identical face, hairstyle, outfit and transparent umbrella from the previous shot, now walking from a Taipei metro exit into a rainy night street. Medium shot, camera slowly dollies backward, wet asphalt reflecting passing cars and signs, realistic body motion, restrained neon, no text, no subtitles.'
PROMPT[2]='Vertical 9:16 cinematic 35mm film. Same young East Asian woman, Mio, identical face, hairstyle and outfit, rainy Taipei night. Close-up as she pauses for half a second and gently turns her head toward the street. A restrained neon reflection moves across her face, subtle emotion: lonely but quietly hopeful. Natural facial motion, no text, no subtitles.'
PROMPT[3]='Vertical 9:16 cinematic 35mm film. Same young East Asian woman, Mio, identical outfit and transparent umbrella, seen from behind walking away into a rainy Taipei night street. Rear wide shot, locked camera, she gradually recedes into wet neon reflections and distant traffic, realistic walking, calm ending, no text, no subtitles.'

declare -a CLIP=()
for i in 0 1 2 3; do
  shot="${SHOT[$i]}"
  log="$RUN_ROOT/$shot.flow.log"
  echo "vision_studio_shot_start=$shot"
  if ! AGENTOS_GOOGLE_MEDIA_PROMPT="${PROMPT[$i]}" bash "$FLOW" >"$log" 2>&1; then
    cat "$log"
    echo "vision_studio_produce=SHOT_GENERATION_FAILED"
    echo "vision_studio_failed_shot=$shot"
    exit 10
  fi
  out="$(awk -F= '/^google_flow_output=/{print substr($0,index($0,"=")+1)}' "$log" | tail -n1)"
  status="$(awk -F= '/^google_flow_generate=/{print $2}' "$log" | tail -n1)"
  if [[ "$status" != "PASS" || -z "$out" || ! -s "$out" ]]; then
    flow_class="$(awk -F= '/^google_flow_runtime_error_class=/{print $2}' "$log" | tail -n1)"
    flow_exc="$(awk -F= '/^google_flow_runtime_exception_type=/{print $2}' "$log" | tail -n1)"
    flow_line="$(awk -F= '/^google_flow_runtime_syntax_line=/{print $2}' "$log" | tail -n1)"
    flow_source="$(awk -F= '/^google_flow_runtime_syntax_source=/{print $2}' "$log" | tail -n1)"
    flow_pyver="$(awk -F= '/^google_flow_python_version=/{print $2}' "$log" | tail -n1)"
    flow_offset="$(awk -F= '/^google_flow_runtime_syntax_offset=/{print $2}' "$log" | tail -n1)"
    flow_stage="$(awk -F= '/^google_flow_stage=/{print $2}' "$log" | tail -n1)"
    flow_host="$(awk -F= '/^google_flow_host=/{print $2}' "$log" | tail -n1)"
    echo "vision_studio_flow_status=${status:-MISSING}"
    if [[ -n "$flow_class" ]]; then echo "vision_studio_flow_error_class=$flow_class"; fi
    if [[ -n "$flow_exc" ]]; then echo "vision_studio_flow_exception_type=$flow_exc"; fi
    if [[ -n "$flow_line" ]]; then echo "vision_studio_flow_syntax_line=$flow_line"; fi
    if [[ -n "$flow_source" ]]; then echo "vision_studio_flow_syntax_source=$flow_source"; fi
    if [[ -n "$flow_pyver" ]]; then echo "vision_studio_flow_python_version=$flow_pyver"; fi
    if [[ -n "$flow_offset" ]]; then echo "vision_studio_flow_syntax_offset=$flow_offset"; fi
    if [[ -n "$flow_stage" ]]; then echo "vision_studio_flow_stage=$flow_stage"; fi
    if [[ -n "$flow_host" ]]; then echo "vision_studio_flow_host=$flow_host"; fi
    echo "vision_studio_produce=SHOT_ARTIFACT_MISSING"
    echo "vision_studio_failed_shot=$shot"
    exit 11
  fi
  CLIP+=("$out")
  echo "vision_studio_shot_pass=$shot"
  echo "vision_studio_shot_source=$out"
done

FINAL="$RUN_ROOT/rain_exit_final_v001.mp4"
RECEIPT="$RUN_ROOT/rain_exit_final_v001.receipt.json"

"$FFMPEG" -y \
  -i "${CLIP[0]}" -i "${CLIP[1]}" -i "${CLIP[2]}" -i "${CLIP[3]}" \
  -f lavfi -t 10 -i "anoisesrc=color=pink:amplitude=0.025:sample_rate=48000" \
  -filter_complex "\
[0:v]trim=duration=2,setpts=PTS-STARTPTS,scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps=24[v0];\
[1:v]trim=duration=3,setpts=PTS-STARTPTS,scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps=24[v1];\
[2:v]trim=duration=2,setpts=PTS-STARTPTS,scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps=24[v2];\
[3:v]trim=duration=3,setpts=PTS-STARTPTS,scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps=24[v3];\
[v0][v1][v2][v3]concat=n=4:v=1:a=0[v];\
[4:a]volume=0.20,afade=t=in:st=0:d=0.3,afade=t=out:st=9.4:d=0.6[a]" \
  -map "[v]" -map "[a]" \
  -c:v libx264 -preset medium -crf 19 -pix_fmt yuv420p \
  -c:a aac -b:a 128k -shortest -movflags +faststart "$FINAL" >"$RUN_ROOT/ffmpeg.log" 2>&1

if [[ ! -s "$FINAL" ]]; then
  cat "$RUN_ROOT/ffmpeg.log"
  echo "vision_studio_produce=ASSEMBLY_FAILED"
  exit 12
fi

sha="$(sha256sum "$FINAL" | awk '{print $1}')"
bytes="$(stat -c '%s' "$FINAL")"
python3 - "$RECEIPT" "$FINAL" "$sha" "$bytes" "${CLIP[@]}" <<'PY'
import json,sys
receipt_path, final_path, sha, size, *clips = sys.argv[1:]
payload = {
  "schema": "agentos.vision-studio-production-receipt/v1",
  "project_id": "rain-exit-v001",
  "ok": True,
  "generator": "media.google-flow",
  "shots": [
    {"shot_id": f"s{i+1:02d}", "source": p, "accepted": True}
    for i,p in enumerate(clips)
  ],
  "final": {
    "path": final_path,
    "sha256": sha,
    "bytes": int(size),
    "duration_seconds": 10,
    "aspect_ratio": "9:16",
    "fps": 24
  },
  "audio": {"type": "synthetic_rain_ambience_mvp"},
  "cost": {"status": "provider_credit_cost_not_yet_measured"},
  "qc": {"status": "REQUIRES_VISUAL_REVIEW"}
}
with open(receipt_path,"w",encoding="utf-8") as f:
    json.dump(payload,f,ensure_ascii=False,indent=2,sort_keys=True)
    f.write("\n")
PY

echo "vision_studio_produce=PASS"
echo "vision_studio_project_id=$PROJECT_ID"
echo "vision_studio_output=$FINAL"
echo "vision_studio_receipt=$RECEIPT"
echo "vision_studio_sha256=$sha"
echo "vision_studio_bytes=$bytes"
