#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import fcntl
import json
import mimetypes
import os
import sys
import tempfile
import importlib.util
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(os.environ.get("AGENTOS_REPO_ROOT", str(Path(__file__).resolve().parents[1]))).expanduser()

def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value

_ENV_SOURCES = [
    ("process", None),
    ("character-fusion", Path.home() / ".config" / "agentos" / "character-fusion.env"),
    ("stable-agentmanager", Path("/home/ubuntu/agentmanager/.env")),
    ("release", REPO_ROOT / ".env"),
    ("invoice-vision", Path("/home/ubuntu/invoice-intake-service/vision.env")),
    ("agentos-secrets", Path.home() / ".agentos.secrets"),
    ("dashboard", Path.home() / ".config" / "milkcat" / "dashboard.env.local"),
]

for _label, _env in _ENV_SOURCES:
    if _env is not None:
        _load_env_file(_env)


def _read_env_value(path: Path, key: str) -> str:
    if not path.is_file():
        return ""
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        k, value = line.split("=", 1)
        if k.strip() != key:
            continue
        return value.strip().strip('"').strip("'")
    return ""


def _gemini_key_candidates() -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()

    process_value = os.environ.get("GEMINI_API_KEY", "").strip()
    if process_value:
        candidates.append(("process", process_value))
        seen.add(process_value)

    for label, path in _ENV_SOURCES:
        if path is None:
            continue
        value = _read_env_value(path, "GEMINI_API_KEY").strip()
        if value and value not in seen:
            candidates.append((label, value))
            seen.add(value)
    return candidates

_RECONCILIATION_PATH = REPO_ROOT / "libs" / "model2ir" / "src" / "model2ir" / "reconciliation.py"
if not _RECONCILIATION_PATH.is_file():
    raise RuntimeError(f"weighted reconciliation module missing: {_RECONCILIATION_PATH}")
_spec = importlib.util.spec_from_file_location("agentos_model2ir_reconciliation", _RECONCILIATION_PATH)
if _spec is None or _spec.loader is None:
    raise RuntimeError("unable to load weighted reconciliation module")
_reconciliation = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _reconciliation
_spec.loader.exec_module(_reconciliation)
ReconciliationPolicy = _reconciliation.ReconciliationPolicy
ReconciliationSource = _reconciliation.ReconciliationSource
weighted_reconcile_ir = _reconciliation.weighted_reconcile_ir

DATA_ROOT = Path(os.environ.get("AGENT_DATA_ROOT", str(Path.home() / "agent-data"))).expanduser()
ROOT = DATA_ROOT / "projects" / "character-fusion"
JOB_DIR = ROOT / "jobs"
ASSET_DIR = ROOT / "assets"
SERIAL_FILE = ROOT / "serials.json"

VISION_MODEL = (
    os.environ.get("GEMINI_CHARACTER_VISION_MODEL")
    or os.environ.get("GEMINI_INVOICE_MODEL")
    or "gemini-3.8-flash"
)
IMAGE_MODEL = os.environ.get("GEMINI_CHARACTER_IMAGE_MODEL", "gemini-3.1-flash-image")
API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    os.close(fd)
    tmp = Path(name)
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def job_path(job_id: str) -> Path:
    if not job_id or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for ch in job_id):
        raise ValueError("invalid job id")
    return JOB_DIR / f"{job_id}.json"


def update_job(job_id: str, **changes: Any) -> dict[str, Any]:
    path = job_path(job_id)
    job = read_json(path)
    for key, value in changes.items():
        if key == "output" and isinstance(value, dict):
            job.setdefault("output", {}).update(value)
        else:
            job[key] = value
    atomic_write(path, job)
    return job


def image_part(path: Path) -> dict[str, Any]:
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    return {
        "inlineData": {
            "mimeType": mime,
            "data": base64.b64encode(path.read_bytes()).decode("ascii"),
        }
    }


def gemini_generate(model: str, parts: list[dict[str, Any]], generation_config: dict[str, Any] | None = None) -> dict[str, Any]:
    candidates = _gemini_key_candidates()
    if not candidates:
        raise RuntimeError("GEMINI_API_KEY is not configured in any governed source")

    payload: dict[str, Any] = {"contents": [{"role": "user", "parts": parts}]}
    if generation_config:
        payload["generationConfig"] = generation_config

    invalid_sources: list[str] = []
    transient_codes = {429, 500, 502, 503, 504}
    max_attempts = max(1, int(os.environ.get("GEMINI_CHARACTER_MAX_ATTEMPTS", "4")))

    for source_label, api_key in candidates:
        for attempt in range(1, max_attempts + 1):
            req = urllib.request.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                method="POST",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": api_key,
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=180) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", "replace")[:3000]
                if exc.code == 400 and ("API_KEY_INVALID" in body or "API key not valid" in body):
                    invalid_sources.append(source_label)
                    break
                if exc.code in transient_codes and attempt < max_attempts:
                    retry_after = exc.headers.get("Retry-After") if exc.headers else None
                    try:
                        delay = min(30.0, max(1.0, float(retry_after))) if retry_after else min(30.0, 2 ** attempt)
                    except ValueError:
                        delay = min(30.0, 2 ** attempt)
                    time.sleep(delay)
                    continue
                raise RuntimeError(
                    f"Gemini HTTP {exc.code} using key source {source_label} after attempt {attempt}/{max_attempts}: {body}"
                ) from exc

    raise RuntimeError(
        "GEMINI_API_KEY is invalid in all governed sources: " + ", ".join(invalid_sources)
    )


def response_parts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = payload.get("candidates") or []
    if not candidates:
        return []
    return ((candidates[0].get("content") or {}).get("parts") or [])


def parse_json_text(payload: dict[str, Any]) -> dict[str, Any]:
    text = "\n".join(str(part.get("text", "")) for part in response_parts(payload) if part.get("text")).strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        if text.startswith("json"):
            text = text[4:].lstrip()
    value = json.loads(text)
    if not isinstance(value, dict):
        raise RuntimeError("vision extractor returned non-object JSON")
    return value


def leaf(value: str, confidence: float = 0.95, status: str = "observed") -> dict[str, Any]:
    return {
        "value": value,
        "confidence": confidence,
        "status": status,
    }


def water_drop_main_ir() -> dict[str, Any]:
    return {
        "schema": "character-ir-candidate/v0.6",
        "body_plan": {
            "kind": "water_drop",
            "confidence": 1.0,
            "source": "preset:water-drop/v1",
        },
        "identity_traits": {
            "material": {"primary": leaf("transparent glossy water")},
            "style": {"primary": leaf("cute minimal chibi mascot")},
            "palette": {"primary": leaf("cyan blue white")},
            "face": {"primary": leaf("simple friendly face integrated into droplet body")},
        },
        "negative_constraints": [
            "no human torso",
            "no human skull inside the droplet",
            "no person wearing a droplet costume",
            "no literal pasted human hair",
        ],
    }


def extract_person_traits(path: Path) -> dict[str, Any]:
    prompt = """
Analyze this person/reference image for character-design transfer.
Return ONLY JSON. Do not identify the person.
Use this exact top-level shape:
{
  "evidence_class":"ip-genome-visual-traits",
  "identity_traits":{
    "hair":{"primary":{"value":"...","confidence":0.0,"status":"observed"}},
    "eyewear":{"primary":{"value":"...","confidence":0.0,"status":"observed"}},
    "palette":{"primary":{"value":"...","confidence":0.0,"status":"observed"}},
    "clothing":{"primary":{"value":"...","confidence":0.0,"status":"observed"}},
    "props":{"primary":{"value":"...","confidence":0.0,"status":"observed"}},
    "companion":{"primary":{"value":"...","confidence":0.0,"status":"observed"}},
    "expression":{"primary":{"value":"...","confidence":0.0,"status":"observed"}}
  },
  "negative_constraints":[]
}
Omit categories that are not visibly supported. Keep descriptions short and visual.
"""
    result = gemini_generate(
        VISION_MODEL,
        [{"text": prompt}, image_part(path)],
        {"responseMimeType": "application/json"},
    )
    return parse_json_text(result)


def extract_custom_main(path: Path) -> dict[str, Any]:
    prompt = """
Analyze this image as a MAIN VISUAL / mascot species reference.
Return ONLY JSON using Character IR candidate shape:
{
  "schema":"character-ir-candidate/v0.6",
  "body_plan":{"kind":"short_snake_case","confidence":0.0,"source":"observed-main-visual"},
  "identity_traits":{
    "material":{"primary":{"value":"...","confidence":0.0,"status":"observed"}},
    "style":{"primary":{"value":"...","confidence":0.0,"status":"observed"}},
    "palette":{"primary":{"value":"...","confidence":0.0,"status":"observed"}},
    "face":{"primary":{"value":"...","confidence":0.0,"status":"observed"}}
  },
  "negative_constraints":[]
}
The body_plan must describe the dominant species/silhouette, not incidental clothing.
"""
    result = gemini_generate(
        VISION_MODEL,
        [{"text": prompt}, image_part(path)],
        {"responseMimeType": "application/json"},
    )
    return parse_json_text(result)


def fuse(main_ir: dict[str, Any], person_ir: dict[str, Any]) -> dict[str, Any]:
    return weighted_reconcile_ir(
        [
            ReconciliationSource("main_visual", main_ir, 0.75),
            ReconciliationSource("person", person_ir, 0.25),
        ],
        ReconciliationPolicy(
            preserve_from={
                "body_plan.kind": "main_visual",
                "identity_traits.material.primary.value": "main_visual",
                "identity_traits.style.primary.value": "main_visual",
            },
            per_field={
                "identity_traits.palette.primary.value": {"main_visual": 0.65, "person": 0.35},
                "identity_traits.hair.primary.value": {"main_visual": 0.55, "person": 0.45},
                "identity_traits.eyewear.primary.value": {"main_visual": 0.20, "person": 0.80},
                "identity_traits.props.primary.value": {"main_visual": 0.10, "person": 0.90},
                "identity_traits.companion.primary.value": {"main_visual": 0.10, "person": 0.90},
                "identity_traits.expression.primary.value": {"main_visual": 0.30, "person": 0.70},
            },
        ),
    )


def render_prompt(target_ir: dict[str, Any], strict: bool = False) -> str:
    extra = (
        "STRICT RETRY: reject any human-shaped torso, human head embedded inside the mascot, "
        "costume-like result, or literal human hair pasted onto the mascot. "
        if strict else ""
    )
    return f"""
Create ONE polished 1:1 character-design image from this target Character IR.
The MAIN VISUAL body plan and material language dominate. Person traits are identity accents only.
Translate transferred traits into the main visual's material language: e.g. a human bun on a water
mascot becomes a water-flow bun silhouette, not literal human hair.
Do not include text, captions, labels, UI, or serial numbers in the image.
Keep a clean simple background and show a single complete character.
{extra}
TARGET CHARACTER IR:
{json.dumps(target_ir, ensure_ascii=False)}
"""


def render_image(target_ir: dict[str, Any], person: Path, main_visual: Path | None, strict: bool) -> bytes:
    parts: list[dict[str, Any]] = [{"text": render_prompt(target_ir, strict=strict)}]
    if main_visual:
        parts.extend([
            {"text": "MAIN VISUAL reference image:"},
            image_part(main_visual),
        ])
    parts.extend([
        {"text": "PERSON identity-trait reference image. Do not preserve human anatomy:"},
        image_part(person),
    ])
    result = gemini_generate(
        IMAGE_MODEL,
        parts,
        {"responseModalities": ["IMAGE"]},
    )
    for part in response_parts(result):
        inline = part.get("inlineData") or {}
        data = inline.get("data")
        if data:
            return base64.b64decode(data)
    raise RuntimeError("image model returned no image")


def inspect_output(image_path: Path) -> dict[str, Any]:
    prompt = """
Inspect this generated mascot image. Return ONLY JSON:
{
  "body_plan":{"kind":"short_snake_case"},
  "material":"short description",
  "eyewear":"short description or none",
  "human_torso_dominant":false,
  "human_head_embedded":false,
  "costume_like":false,
  "literal_human_hair":false
}
Judge what is visibly present, not what the prompt intended.
"""
    return parse_json_text(
        gemini_generate(
            VISION_MODEL,
            [{"text": prompt}, image_part(image_path)],
            {"responseMimeType": "application/json"},
        )
    )


def accept(preset: str, target: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    expected = ((target.get("body_plan") or {}).get("kind") or "").strip()
    actual_kind = ((actual.get("body_plan") or {}).get("kind") or "").strip()
    checks = {
        "body_plan": actual_kind == expected if expected else True,
        "no_human_torso": not bool(actual.get("human_torso_dominant")),
        "no_embedded_head": not bool(actual.get("human_head_embedded")),
        "not_costume": not bool(actual.get("costume_like")),
        "no_literal_human_hair": not bool(actual.get("literal_human_hair")),
    }
    if preset != "water-drop":
        checks["body_plan"] = bool(actual_kind)
    return {
        "pass": all(checks.values()),
        "checks": checks,
        "expectedBodyPlan": expected,
        "actualBodyPlan": actual_kind,
    }


def allocate_serial(preset: str) -> str:
    ROOT.mkdir(parents=True, exist_ok=True)
    prefix = {
        "water-drop": "DROP",
        "slime": "SLIME",
        "leopard-cat": "CAT",
        "robot": "BOT",
    }.get(preset, "CHAR")
    SERIAL_FILE.touch(exist_ok=True)
    with SERIAL_FILE.open("r+", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        raw = fh.read().strip()
        state = json.loads(raw) if raw else {}
        number = int(state.get(prefix, 0)) + 1
        state[prefix] = number
        fh.seek(0)
        fh.truncate()
        json.dump(state, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    return f"{prefix}-{number:06d}"


def run(job_id: str) -> None:
    path = job_path(job_id)
    job = read_json(path)
    person = Path(job["input"]["personAsset"])
    main_visual = Path(job["input"]["mainVisualAsset"]) if job["input"].get("mainVisualAsset") else None
    preset = str(job.get("preset") or "water-drop")
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    output = ASSET_DIR / f"{job_id}.png"

    try:
        update_job(job_id, status="extracting", startedAt=now())
        if preset == "water-drop" and main_visual is None:
            main_ir = water_drop_main_ir()
        elif main_visual:
            main_ir = extract_custom_main(main_visual)
        else:
            raise RuntimeError("custom preset requires main visual image")

        person_ir = extract_person_traits(person)
        target_ir = fuse(main_ir, person_ir)
        update_job(job_id, status="rendering", output={"targetIr": target_ir})

        final_actual = None
        final_acceptance = None
        for attempt in range(2):
            data = render_image(target_ir, person, main_visual, strict=attempt > 0)
            output.write_bytes(data)
            os.chmod(output, 0o600)
            update_job(job_id, status="validating")
            actual = inspect_output(output)
            acceptance = accept(preset, target_ir, actual)
            final_actual = actual
            final_acceptance = {**acceptance, "attempt": attempt + 1}
            if acceptance["pass"]:
                break
            update_job(job_id, status="rendering")

        if not final_acceptance or not final_acceptance["pass"]:
            raise RuntimeError("generated image failed Character IR preservation checks after retry")

        serial = allocate_serial(preset)
        update_job(
            job_id,
            status="ready",
            completedAt=now(),
            output={
                "asset": str(output),
                "serial": serial,
                "actualIr": final_actual,
                "acceptance": final_acceptance,
                "provider": f"gemini:{IMAGE_MODEL}",
            },
        )
    except Exception as exc:
        update_job(
            job_id,
            status="failed",
            failedAt=now(),
            error={"code": type(exc).__name__, "message": str(exc)[:2000]},
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args()
    run(args.job_id)


if __name__ == "__main__":
    main()
