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
import subprocess
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

_HF_ENV_SOURCES = [
    Path.home() / ".config" / "agentos" / "mio-tryon.env",
    Path.home() / ".agentos.secrets",
    Path("/home/ubuntu/agentmanager/.env"),
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


def _resolve_hf_token() -> str:
    direct = (os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN") or "").strip()
    if direct:
        return direct
    for path in _HF_ENV_SOURCES:
        for key in ("HF_TOKEN", "HUGGINGFACE_TOKEN"):
            value = _read_env_value(path, key).strip()
            if value:
                return value
    return ""


def _parse_loose_json_text(text: str) -> dict[str, Any]:
    value = text.strip()
    if value.startswith("```"):
        value = value.split("\n", 1)[1] if "\n" in value else value
        if value.endswith("```"):
            value = value[:-3]
        value = value.strip()
        if value.startswith("json"):
            value = value[4:].lstrip()
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise RuntimeError("VLM fallback returned non-object JSON")
    return parsed


def _hf_vlm_json(prompt: str, image_path: Path) -> dict[str, Any]:
    token = _resolve_hf_token()
    if not token:
        raise RuntimeError("HF_TOKEN is not configured for Character Fusion vision fallback")

    python_bin = Path("/home/ubuntu/.local/share/mio-tryon-venv/bin/python")
    if not python_bin.is_file():
        raise RuntimeError("Mio try-on inference venv is unavailable for Character Fusion vision fallback")

    model = os.environ.get("HF_CHARACTER_VISION_MODEL", "Qwen/Qwen2.5-VL-3B-Instruct")
    with tempfile.TemporaryDirectory(prefix="character-fusion-hf-vlm-") as tmp:
        prompt_path = Path(tmp) / "prompt.txt"
        prompt_path.write_text(prompt, encoding="utf-8")
        helper = r'''
import base64
import json
import mimetypes
import os
import sys
from pathlib import Path

import httpx
from huggingface_hub import InferenceClient

prompt = Path(sys.argv[1]).read_text(encoding="utf-8")
image_path = Path(sys.argv[2])
preferred = sys.argv[3].strip()
mime = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
data = base64.b64encode(image_path.read_bytes()).decode("ascii")
image_url = f"data:{mime};base64,{data}"
token = os.environ["HF_TOKEN"]

candidates = []
if preferred:
    candidates.append(preferred)

try:
    response = httpx.get(
        "https://router.huggingface.co/v1/models",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    response.raise_for_status()
    catalog = response.json().get("data") or []
    for entry in catalog:
        architecture = entry.get("architecture") or {}
        modalities = architecture.get("input_modalities") or []
        model_id = entry.get("id")
        providers = entry.get("providers") or []
        if model_id and "image" in modalities and any((p.get("status") or "") == "live" for p in providers):
            if model_id not in candidates:
                candidates.append(model_id)
except Exception:
    pass

fallbacks = [
    "zai-org/GLM-5.3-Flash:baseten",
    "deepseek-ai/DeepSeek-V4.1-Flash:baseten",
    "meta-llama/Llama-3.2-11B-Vision-Instruct",
]
for model_id in fallbacks:
    if model_id not in candidates:
        candidates.append(model_id)

client = InferenceClient(api_key=token, provider="auto")
errors = []
for model_id in candidates[:12]:
    try:
        result = client.chat.completions.create(
            model=model_id,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image_url}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            max_tokens=1400,
            temperature=0.1,
        )
        content = result.choices[0].message.content
        if isinstance(content, str) and content.strip():
            print(content)
            raise SystemExit(0)
        errors.append(f"{model_id}: empty response")
    except Exception as exc:
        errors.append(f"{model_id}: {type(exc).__name__}: {exc}")

raise RuntimeError("No HF VLM succeeded: " + " | ".join(errors[-6:]))
'''
        proc = subprocess.run(
            [str(python_bin), "-c", helper, str(prompt_path), str(image_path), model],
            env={**os.environ, "HF_TOKEN": token},
            capture_output=True,
            text=True,
            timeout=240,
        )
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "")[-3000:]
            raise RuntimeError(f"Hugging Face vision fallback failed: {tail}")
        return _parse_loose_json_text(proc.stdout)


def _should_fallback_from_gemini(exc: Exception) -> bool:
    message = str(exc)
    markers = (
        "Gemini HTTP 429",
        "Gemini HTTP 500",
        "Gemini HTTP 502",
        "Gemini HTTP 503",
        "Gemini HTTP 504",
        "RESOURCE_EXHAUSTED",
        "quota",
        "GEMINI_API_KEY is not configured",
        "GEMINI_API_KEY is invalid",
        "Gemini transport timeout/unavailable",
    )
    return any(marker in message for marker in markers)

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
            request_timeout = max(
                10.0,
                float(os.environ.get("GEMINI_CHARACTER_REQUEST_TIMEOUT", "45")),
            )
            try:
                with urllib.request.urlopen(req, timeout=request_timeout) as response:
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
            except (TimeoutError, urllib.error.URLError) as exc:
                if attempt < max_attempts:
                    time.sleep(min(15.0, 2 ** attempt))
                    continue
                raise RuntimeError(
                    "Gemini transport timeout/unavailable "
                    f"using key source {source_label} after attempt "
                    f"{attempt}/{max_attempts}: {type(exc).__name__}: {exc}"
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
    try:
        result = gemini_generate(
            VISION_MODEL,
            [{"text": prompt}, image_part(path)],
            {"responseMimeType": "application/json"},
        )
        return parse_json_text(result)
    except RuntimeError as exc:
        if not _should_fallback_from_gemini(exc):
            raise
        return _hf_vlm_json(prompt, path)


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
    try:
        result = gemini_generate(
            VISION_MODEL,
            [{"text": prompt}, image_part(path)],
            {"responseMimeType": "application/json"},
        )
        return parse_json_text(result)
    except RuntimeError as exc:
        if not _should_fallback_from_gemini(exc):
            raise
        return _hf_vlm_json(prompt, path)


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


def _render_image_gemini_web(target_ir: dict[str, Any], strict: bool) -> bytes:
    python_bin = Path.home() / ".local/share/agentos/gui-worker/venv/bin/python"
    if not python_bin.is_file():
        raise RuntimeError("Gemini Web GUI worker venv is unavailable")

    prompt = render_prompt(target_ir, strict=strict) + """
Use your image-generation capability now. Return a generated image, not a text description.
The result must be a single polished mascot on a simple clean background.
"""
    with tempfile.TemporaryDirectory(prefix="character-fusion-gemini-web-") as tmp:
        prompt_path = Path(tmp) / "prompt.txt"
        output_path = Path(tmp) / "output.png"
        prompt_path.write_text(prompt, encoding="utf-8")
        helper = r'''
import fcntl
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

prompt = Path(sys.argv[1]).read_text(encoding="utf-8")
output = Path(sys.argv[2])
lock_path = Path("/home/ubuntu/agent-data/runtime/locks/oracle-gui-profile.lock")
lock_path.parent.mkdir(parents=True, exist_ok=True)

composer_selectors = [
    'rich-textarea div[contenteditable="true"]',
    'textarea[aria-label*="prompt" i]',
    '[contenteditable="true"][aria-label*="prompt" i]',
    'div.ql-editor[contenteditable="true"]',
    'textarea',
    '[contenteditable="true"]',
]
image_selectors = [
    'model-response img',
    '[data-test-id*="model-response"] img',
    '.model-response-text img',
    'message-content img',
    'img[alt*="generated" i]',
]

def first_visible(page, selectors):
    for selector in selectors:
        try:
            loc = page.locator(selector)
            for i in range(min(loc.count(), 16)):
                item = loc.nth(i)
                try:
                    if item.is_visible(timeout=250):
                        return item
                except Exception:
                    pass
        except Exception:
            pass
    return None

def candidates(page):
    rows = []
    seen = set()
    for selector in image_selectors:
        try:
            loc = page.locator(selector)
            for i in range(loc.count()):
                item = loc.nth(i)
                try:
                    if not item.is_visible(timeout=200):
                        continue
                    box = item.bounding_box()
                    if not box or box.get("width", 0) < 180 or box.get("height", 0) < 180:
                        continue
                    key = (selector, i, round(box.get("width", 0)), round(box.get("height", 0)))
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append(item)
                except Exception:
                    pass
        except Exception:
            pass
    return rows

with lock_path.open("a+") as lock:
    fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        if not browser.contexts:
            raise RuntimeError("gemini_web_no_browser_context")
        pages = [x for x in browser.contexts[0].pages if "gemini.google.com" in str(x.url or "")]
        if not pages:
            raise RuntimeError("gemini_web_no_session")
        page = next((x for x in pages if first_visible(x, composer_selectors) is not None), pages[0])
        page.bring_to_front()
        composer = first_visible(page, composer_selectors)
        if composer is None:
            raise RuntimeError("gemini_web_composer_not_found")

        baseline = len(candidates(page))
        try:
            composer.fill(prompt)
        except Exception:
            composer.click()
            page.keyboard.press("ControlOrMeta+A")
            page.keyboard.type(prompt)
        page.keyboard.press("Enter")

        deadline = time.monotonic() + 180
        chosen = None
        while time.monotonic() < deadline:
            rows = candidates(page)
            if len(rows) > baseline:
                chosen = rows[-1]
                break
            time.sleep(1.5)

        if chosen is None:
            raise TimeoutError("gemini_web_image_response_timeout")

        chosen.scroll_into_view_if_needed()
        chosen.screenshot(path=str(output), type="png")
        if not output.is_file() or output.stat().st_size < 10000:
            raise RuntimeError("gemini_web_image_capture_invalid")
        print("character_fusion_gemini_web_render=PASS")
'''
        proc = subprocess.run(
            [str(python_bin), "-c", helper, str(prompt_path), str(output_path)],
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=240,
        )
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "")[-3000:]
            raise RuntimeError(f"Gemini Web image fallback failed: {tail}")
        data = output_path.read_bytes()
        if len(data) < 10000:
            raise RuntimeError("Gemini Web image fallback returned an unexpectedly small image")
        return data


def _render_image_hf(target_ir: dict[str, Any], strict: bool) -> bytes:
    token = _resolve_hf_token()
    if not token:
        raise RuntimeError("HF_TOKEN is not configured for Character Fusion image fallback")

    python_bin = Path("/home/ubuntu/.local/share/mio-tryon-venv/bin/python")
    if not python_bin.is_file():
        raise RuntimeError("Mio try-on inference venv is unavailable for Character Fusion fallback")

    model = os.environ.get("HF_CHARACTER_IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell")
    prompt = render_prompt(target_ir, strict=strict) + """
Render as a polished mascot illustration. The subject MUST be the non-human mascot species in the
target body_plan. Human traits may appear only as stylized accessories or material-native motifs.
No human body, no human inside costume, no literal human hair.
"""
    with tempfile.TemporaryDirectory(prefix="character-fusion-hf-") as tmp:
        prompt_path = Path(tmp) / "prompt.txt"
        output_path = Path(tmp) / "output.png"
        prompt_path.write_text(prompt, encoding="utf-8")
        helper = r'''
import os
import sys
from pathlib import Path
from huggingface_hub import InferenceClient

prompt = Path(sys.argv[1]).read_text(encoding="utf-8")
out = Path(sys.argv[2])
model = sys.argv[3]
client = InferenceClient(api_key=os.environ["HF_TOKEN"], provider="auto")
image = client.text_to_image(
    prompt,
    model=model,
    width=1024,
    height=1024,
)
image.save(out, format="PNG")
'''
        proc = subprocess.run(
            [str(python_bin), "-c", helper, str(prompt_path), str(output_path), model],
            env={**os.environ, "HF_TOKEN": token},
            capture_output=True,
            text=True,
            timeout=240,
        )
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "")[-3000:]
            raise RuntimeError(f"Hugging Face image fallback failed: {tail}")
        data = output_path.read_bytes()
        if len(data) < 10000:
            raise RuntimeError("Hugging Face image fallback returned an unexpectedly small image")
        return data


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
    try:
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
    except RuntimeError as exc:
        message = str(exc)
        fallback_reasons = (
            "Gemini HTTP 429",
            "Gemini HTTP 500",
            "Gemini HTTP 502",
            "Gemini HTTP 503",
            "Gemini HTTP 504",
            "RESOURCE_EXHAUSTED",
            "quota",
        )
        if not any(reason in message for reason in fallback_reasons):
            raise
        try:
            return _render_image_hf(target_ir, strict=strict)
        except RuntimeError as hf_exc:
            hf_message = str(hf_exc)
            if not any(marker in hf_message for marker in (
                "402 Payment Required",
                "depleted your monthly included credits",
                "quota",
                "rate",
                "unavailable",
                "timeout",
            )):
                raise
            return _render_image_gemini_web(target_ir, strict=strict)


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
    try:
        return parse_json_text(
            gemini_generate(
                VISION_MODEL,
                [{"text": prompt}, image_part(image_path)],
                {"responseMimeType": "application/json"},
            )
        )
    except RuntimeError as exc:
        if not _should_fallback_from_gemini(exc):
            raise
        return _hf_vlm_json(prompt, image_path)


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
