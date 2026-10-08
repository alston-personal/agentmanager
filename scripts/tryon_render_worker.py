#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import hashlib
import inspect
import io
import time
import shutil
import signal
import tempfile
import urllib.request
import urllib.parse
from html.parser import HTMLParser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gradio_client import Client, handle_file
from PIL import Image, ImageOps

try:
    from huggingface_hub import InferenceClient
except Exception:
    InferenceClient = None

SCHEMA = "agentos.tryon-render-job/v1"
SPACE_ID = os.environ.get("AGENTOS_TRYON_SPACE_ID", "yisol/IDM-VTON")
ANY_ITEM_SPACE_IDS = [
    value.strip()
    for value in os.environ.get(
        "AGENTOS_TRYON_ANY_ITEM_SPACE_IDS",
        "pbgo/OmniTry,Kunbyte/OmniTry",
    ).split(",")
    if value.strip()
]
HF_TOKEN = (os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN") or "").strip() or None
DATA_ROOT = Path(os.environ.get("AGENT_DATA_ROOT", str(Path.home() / "agent-data"))).expanduser()
JOB_DIR = DATA_ROOT / "projects" / "dressup-simulator" / "render_jobs" / "runtime"
CURRENT_DIR = DATA_ROOT / "projects" / "dressup-simulator" / "current_outfits"
ASSET_DIR = DATA_ROOT / "projects" / "dressup-simulator" / "render_assets"
CACHE_DIR = DATA_ROOT / "projects" / "dressup-simulator" / "render_cache"
BASE_BODY_URL = os.environ.get(
    "AGENTOS_MIO_BASE_BODY_URL",
    "https://studio.milkcat.org/personas/mio/mio-base-v2.webp",
)

LAYER_TIMEOUT_SECONDS = int(os.environ.get("AGENTOS_TRYON_LAYER_TIMEOUT_SECONDS", "180"))
PROVIDER_TIMEOUT_SECONDS = float(os.environ.get("AGENTOS_TRYON_PROVIDER_TIMEOUT_SECONDS", "120"))


class LayerTimeoutError(TimeoutError):
    pass


def _layer_timeout_handler(signum, frame):
    raise LayerTimeoutError(f"layer render exceeded {LAYER_TIMEOUT_SECONDS}s")

CLOTHING_SUPPORTED = {
    "upper_inner": "upper garment",
    "upper_main": "upper garment",
    "upper_outer": "outerwear",
    "lower_main": "lower garment",
    "onepiece": "one-piece garment",
}

ANY_ITEM_SUPPORTED = {
    "shoes": "shoe",
    "bag": "bag",
}

ORDER = [
    "upper_inner",
    "upper_main",
    "lower_main",
    "onepiece",
    "upper_outer",
    "shoes",
    "bag",
]


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
_ANY_ITEM_CLIENTS: dict[str, Client] = {}
_QWEN_EDIT_CLIENT: Client | None = None
QWEN_EDIT_SPACE_ID = os.environ.get(
    "AGENTOS_TRYON_QWEN_EDIT_SPACE_ID",
    "Qwen/Qwen-Image-2.1-workflow",
)
INFERENCE_PROVIDER_ROUTES = []
for _route in os.environ.get(
    "AGENTOS_TRYON_INFERENCE_PROVIDER_ROUTES",
    "fal-ai:Qwen/Qwen-Image-Edit,wavespeed:Qwen/Qwen-Image-Edit-2511",
).split(","):
    _route = _route.strip()
    if not _route or ":" not in _route:
        continue
    _provider, _model = _route.split(":", 1)
    if _provider.strip() and _model.strip():
        INFERENCE_PROVIDER_ROUTES.append((_provider.strip(), _model.strip()))


def client() -> Client:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = Client(
            SPACE_ID,
            download_files=True,
            verbose=False,
            httpx_kwargs={"timeout": PROVIDER_TIMEOUT_SECONDS},
        )
    return _CLIENT


def any_item_client(space_id: str) -> Client:
    cached = _ANY_ITEM_CLIENTS.get(space_id)
    if cached is None:
        client_kwargs = {
            "download_files": True,
            "verbose": False,
            "httpx_kwargs": {"timeout": PROVIDER_TIMEOUT_SECONDS},
        }
        if HF_TOKEN:
            params = inspect.signature(Client).parameters
            if "token" in params:
                client_kwargs["token"] = HF_TOKEN
            elif "hf_token" in params:
                client_kwargs["hf_token"] = HF_TOKEN
        cached = Client(space_id, **client_kwargs)
        _ANY_ITEM_CLIENTS[space_id] = cached
    return cached


def qwen_edit_client() -> Client:
    global _QWEN_EDIT_CLIENT
    if _QWEN_EDIT_CLIENT is None:
        client_kwargs = {
            "download_files": True,
            "verbose": False,
            "httpx_kwargs": {"timeout": PROVIDER_TIMEOUT_SECONDS},
        }
        if HF_TOKEN:
            params = inspect.signature(Client).parameters
            if "token" in params:
                client_kwargs["token"] = HF_TOKEN
            elif "hf_token" in params:
                client_kwargs["hf_token"] = HF_TOKEN
        _QWEN_EDIT_CLIENT = Client(QWEN_EDIT_SPACE_ID, **client_kwargs)
    return _QWEN_EDIT_CLIENT


class _ImageMetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.image_url: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.image_url or tag.lower() != "meta":
            return
        row = {str(k).lower(): (v or "") for k, v in attrs}
        prop = row.get("property") or row.get("name")
        if prop and prop.lower() in {"og:image", "twitter:image", "twitter:image:src"} and row.get("content"):
            self.image_url = row["content"].strip()


def resolve_input_image_url(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 AgentOS-Mio-TryOn/1.5",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        content_type = (resp.headers.get("Content-Type") or "").lower()
        final_url = resp.geturl()
        if "image" in content_type:
            return final_url
        if "html" not in content_type:
            raise RuntimeError(f"input URL is neither image nor HTML: {content_type}")
        body = resp.read(2_000_000).decode(resp.headers.get_content_charset() or "utf-8", "replace")

    parser = _ImageMetaParser()
    parser.feed(body)
    if not parser.image_url:
        raise RuntimeError("product page has no og:image/twitter:image")
    return urllib.parse.urljoin(final_url, parser.image_url)


def download_input(url: str, suffix: str) -> Path:
    image_url = resolve_input_image_url(url)
    req = urllib.request.Request(image_url, headers={"User-Agent": "AgentOS-Mio-TryOn/1.5"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        content_type = (resp.headers.get("Content-Type") or "").lower()
        if "image" not in content_type:
            raise RuntimeError(f"resolved input is not image content: {content_type}")
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
        raise RuntimeError(f"try-on provider returned no output path: {result!r}")
    path = Path(candidate)
    if not path.exists() or path.stat().st_size < 1000:
        raise RuntimeError(f"try-on provider output missing or too small: {candidate}")
    return path


def _dhash(path: Path, crop: tuple[int, int, int, int] | None = None) -> int:
    image = Image.open(path).convert("L")
    if crop is not None:
        image = image.crop(crop)
    image = ImageOps.autocontrast(image)
    image = image.resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(image.getdata())
    value = 0
    bit = 0
    for y in range(8):
        row = y * 9
        for x in range(8):
            if pixels[row + x] > pixels[row + x + 1]:
                value |= 1 << bit
            bit += 1
    return value


def _hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def stray_reference_score(output_path: Path, object_path: Path) -> int:
    """Return lower-is-more-suspicious dHash distance for detached reference object."""
    reference = _dhash(object_path)
    with Image.open(output_path) as image:
        w, h = image.size
    crops = [
        (w // 2, 0, w, h),
        (w * 3 // 5, 0, w, h),
        (w // 2, 0, w, h * 2 // 3),
        (w // 2, h // 3, w, h),
        (w * 3 // 5, h // 5, w, h * 4 // 5),
    ]
    return min(_hamming(reference, _dhash(output_path, crop)) for crop in crops)


def reject_detached_reference(output: str, object_path: Path, object_class: str) -> str:
    output_file = output_path(output)
    # Bags and shoes are especially prone to reference-board leakage: a provider
    # can copy the product beside the person while still returning a valid image.
    if object_class in {"bag", "shoe"}:
        score = stray_reference_score(output_file, object_path)
        if score <= 10:
            raise RuntimeError(
                f"detached_reference_object_detected:{object_class}:dhash_distance={score}"
            )
    return str(output_file)


def _layer_crop_box(width: int, height: int, layer: str) -> tuple[int, int, int, int]:
    boxes = {
        "upper_inner": (0.24, 0.18, 0.76, 0.55),
        "upper_main": (0.24, 0.18, 0.76, 0.58),
        "upper_outer": (0.18, 0.15, 0.82, 0.62),
        "lower_main": (0.22, 0.46, 0.78, 0.84),
        "onepiece": (0.22, 0.22, 0.78, 0.84),
        "shoes": (0.18, 0.76, 0.82, 1.00),
    }
    x1, y1, x2, y2 = boxes.get(layer, (0.20, 0.20, 0.80, 0.85))
    return (
        max(0, int(width * x1)),
        max(0, int(height * y1)),
        min(width, int(width * x2)),
        min(height, int(height * y2)),
    )


def _median_rgb(path: Path, layer: str) -> tuple[int, int, int]:
    image = Image.open(path).convert("RGB")
    crop = image.crop(_layer_crop_box(image.width, image.height, layer))
    crop = ImageOps.contain(crop, (96, 96), method=Image.Resampling.LANCZOS)
    pixels = list(crop.getdata())
    if not pixels:
        return (0, 0, 0)
    channels = list(zip(*pixels))
    med = []
    for channel in channels:
        values = sorted(int(v) for v in channel)
        med.append(values[len(values) // 2])
    return tuple(med)  # type: ignore[return-value]


def _rgb_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return sum((float(x) - float(y)) ** 2 for x, y in zip(a, b)) ** 0.5


def reject_gross_layer_mismatch(output: str, reference_path: Path, layer: str) -> str:
    """Reject only obvious appearance drift; semantic QC remains a separate gate."""
    if layer not in {"upper_inner", "upper_main", "upper_outer", "lower_main", "onepiece", "shoes"}:
        return str(output_path(output))
    output_file = output_path(output)
    ref_rgb = _median_rgb(reference_path, layer)
    out_rgb = _median_rgb(output_file, layer)
    distance = _rgb_distance(ref_rgb, out_rgb)
    ref_luma = sum(ref_rgb) / 3.0
    out_luma = sum(out_rgb) / 3.0
    luma_delta = abs(ref_luma - out_luma)
    # Intentionally conservative: this is for egregious color/value drift such
    # as black trousers becoming beige shorts or white shoes becoming bare feet.
    if distance >= 125.0 and luma_delta >= 55.0:
        raise RuntimeError(
            f"gross_layer_appearance_mismatch:{layer}:rgb_distance={distance:.1f}:luma_delta={luma_delta:.1f}"
        )
    return str(output_file)


def idm_try_on(person_source: str, garment_url: str, description: str, seed: int, layer: str) -> str:
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
            {
                "background": handle_file(str(person_path)),
                "layers": [],
                "composite": None,
            },
            handle_file(str(garment_path)),
            description,
            True,
            False,
            20,
            int(seed),
            api_name="/tryon",
        )
        candidate = str(output_path(result))
        return reject_gross_layer_mismatch(candidate, garment_path, layer)
    finally:
        for path in temp_inputs:
            try:
                path.unlink()
            except FileNotFoundError:
                pass


def build_reference_board(person_path: Path, object_path: Path) -> Path:
    person = Image.open(person_path).convert("RGB")
    product = Image.open(object_path).convert("RGB")

    board_w, board_h = 1536, 1536
    person_box = (80, 80, 1000, 1456)
    product_box = (1060, 420, 1496, 1116)

    board = Image.new("RGB", (board_w, board_h), "white")
    person_fit = ImageOps.contain(
        person,
        (person_box[2] - person_box[0], person_box[3] - person_box[1]),
        method=Image.Resampling.LANCZOS,
    )
    product_fit = ImageOps.contain(
        product,
        (product_box[2] - product_box[0], product_box[3] - product_box[1]),
        method=Image.Resampling.LANCZOS,
    )

    person_xy = (
        person_box[0] + (person_box[2] - person_box[0] - person_fit.width) // 2,
        person_box[1] + (person_box[3] - person_box[1] - person_fit.height) // 2,
    )
    product_xy = (
        product_box[0] + (product_box[2] - product_box[0] - product_fit.width) // 2,
        product_box[1] + (product_box[3] - product_box[1] - product_fit.height) // 2,
    )
    board.paste(person_fit, person_xy)
    board.paste(product_fit, product_xy)

    fd, name = tempfile.mkstemp(prefix="mio-reference-board-", suffix=".jpg")
    os.close(fd)
    path = Path(name)
    board.save(path, format="JPEG", quality=95)
    return path


def inference_provider_reference_try_on(
    person_source: str,
    object_url: str,
    object_class: str,
    seed: int,
    layer: str | None = None,
) -> tuple[str, str]:
    if not HF_TOKEN:
        raise RuntimeError("HF_TOKEN not configured for Inference Providers")
    if InferenceClient is None:
        raise RuntimeError("huggingface_hub InferenceClient is unavailable")
    if not INFERENCE_PROVIDER_ROUTES:
        raise RuntimeError("no Inference Provider routes configured")

    temp_inputs: list[Path] = []
    errors: list[str] = []
    try:
        if person_source.startswith(("http://", "https://")):
            person_path = download_input(person_source, ".webp")
            temp_inputs.append(person_path)
        else:
            person_path = Path(person_source)
            if not person_path.exists():
                raise RuntimeError(f"person input missing: {person_source}")

        if object_url.startswith(("http://", "https://")):
            object_path = download_input(object_url, ".jpg")
            temp_inputs.append(object_path)
        else:
            object_path = Path(object_url)
            if not object_path.exists():
                raise RuntimeError(f"object input missing: {object_url}")

        board_path = build_reference_board(person_path, object_path)
        temp_inputs.append(board_path)

        target = "shoes" if object_class == "shoe" else object_class
        instruction = (
            "The large full-body person on the left is the canonical subject. "
            "The product on the right is a reference item only and must disappear as a separate object. "
            f"Create one final photorealistic full-body image of the left person naturally wearing the exact {target} "
            "from the right reference. Preserve the person's face, identity, hair, body proportions, pose, all other "
            "clothing, hands, background, framing, and lighting. Change only the requested wearable item. Preserve the "
            "product's exact color, silhouette, material, and design. The product reference must be physically attached "
            "to or worn by the person in its natural location. Never leave a second detached copy of the product anywhere "
            "beside the person. Remove the reference-board layout and output only one full-body person."
        )
        board_bytes = board_path.read_bytes()

        for provider, model in INFERENCE_PROVIDER_ROUTES:
            try:
                client = InferenceClient(
                    provider=provider,
                    api_key=HF_TOKEN,
                    timeout=PROVIDER_TIMEOUT_SECONDS,
                )
                result = client.image_to_image(
                    board_bytes,
                    prompt=instruction,
                    model=model,
                )
                fd, name = tempfile.mkstemp(prefix="mio-hf-provider-", suffix=".webp")
                os.close(fd)
                output = Path(name)
                if isinstance(result, Image.Image):
                    image = result.convert("RGB")
                elif isinstance(result, (bytes, bytearray)):
                    image = Image.open(io.BytesIO(bytes(result))).convert("RGB")
                else:
                    raise RuntimeError(f"unexpected image_to_image result: {type(result).__name__}")
                image.save(output, format="WEBP", quality=95, method=6)
                if output.stat().st_size < 1000:
                    output.unlink(missing_ok=True)
                    raise RuntimeError("Inference Provider output is unexpectedly small")
                validated = reject_detached_reference(str(output), object_path, object_class)
                if layer:
                    validated = reject_gross_layer_mismatch(validated, object_path, layer)
                return validated, f"{provider}:{model}"
            except Exception as exc:
                errors.append(f"{provider}:{model}={type(exc).__name__}:{exc}"[:700])

        raise RuntimeError("Inference Providers failed: " + " | ".join(errors))
    finally:
        for path in temp_inputs:
            try:
                path.unlink()
            except FileNotFoundError:
                pass


def qwen_reference_try_on(
    person_source: str,
    object_url: str,
    object_class: str,
    seed: int,
    layer: str | None = None,
) -> tuple[str, str]:
    temp_inputs: list[Path] = []
    global _QWEN_EDIT_CLIENT
    try:
        if person_source.startswith(("http://", "https://")):
            person_path = download_input(person_source, ".webp")
            temp_inputs.append(person_path)
        else:
            person_path = Path(person_source)
            if not person_path.exists():
                raise RuntimeError(f"person input missing: {person_source}")

        if object_url.startswith(("http://", "https://")):
            object_path = download_input(object_url, ".jpg")
            temp_inputs.append(object_path)
        else:
            object_path = Path(object_url)
            if not object_path.exists():
                raise RuntimeError(f"object input missing: {object_url}")

        board_path = build_reference_board(person_path, object_path)
        temp_inputs.append(board_path)

        target = "shoes" if object_class == "shoe" else object_class
        instruction = (
            "The large full-body person on the left is the canonical subject. "
            "The isolated product on the right is a reference item only and must not remain as a separate object. "
            f"Create one final full-body image of the left person naturally wearing the exact {target} from the right reference. "
            "Preserve the person's face, identity, hair, body proportions, pose, all other clothing, hands, background style, "
            "framing, and lighting. Change only the requested wearable item. Preserve the product's exact color, shape, material, "
            "and design. The requested item must be physically worn/carried by the person in its natural location. "
            "A detached duplicate or separate product anywhere beside the person is invalid. Remove the reference-board "
            "layout and the separate product. Output only one photorealistic full-body person."
        )

        result = qwen_edit_client().predict(
            handle_file(str(board_path)),
            instruction,
            api_name="/rewritten_instruction",
        )
        if not isinstance(result, (list, tuple)) or len(result) < 2:
            raise RuntimeError(f"Qwen workflow returned unexpected result: {result!r}")
        edited = result[1]
        validated = reject_detached_reference(str(output_path(edited)), object_path, object_class)
        if layer:
            validated = reject_gross_layer_mismatch(validated, object_path, layer)
        return validated, QWEN_EDIT_SPACE_ID
    except Exception:
        _QWEN_EDIT_CLIENT = None
        raise
    finally:
        for path in temp_inputs:
            try:
                path.unlink()
            except FileNotFoundError:
                pass

def omni_try_on(
    person_source: str,
    object_url: str,
    object_class: str,
    seed: int,
    progress_cb=None,
    layer: str | None = None,
) -> tuple[str, str]:
    temp_inputs: list[Path] = []
    errors: list[str] = []
    try:
        if person_source.startswith(("http://", "https://")):
            person_path = download_input(person_source, ".webp")
            temp_inputs.append(person_path)
        else:
            person_path = Path(person_source)
            if not person_path.exists():
                raise RuntimeError(f"person input missing: {person_source}")

        object_path = download_input(object_url, ".jpg")
        temp_inputs.append(object_path)

        for space_id in ANY_ITEM_SPACE_IDS:
            for attempt in range(1, 3):
                try:
                    if progress_cb:
                        progress_cb(f"Trying {space_id} attempt {attempt}/2")
                    result = any_item_client(space_id).predict(
                        handle_file(str(person_path)),
                        handle_file(str(object_path)),
                        object_class,
                        20,
                        30,
                        int(seed),
                        api_name="/generate",
                    )
                    candidate = str(output_path(result))
                    validated = reject_detached_reference(candidate, object_path, object_class)
                    if layer:
                        validated = reject_gross_layer_mismatch(validated, object_path, layer)
                    return validated, space_id
                except Exception as exc:
                    message = f"{type(exc).__name__}:{exc}"
                    transient = any(
                        marker in message.lower()
                        for marker in (
                            "502 bad gateway",
                            "503 service unavailable",
                            "504 gateway timeout",
                            "connection reset",
                            "temporarily unavailable",
                        )
                    )
                    errors.append(
                        f"{space_id}[attempt={attempt}]={message}"[:500]
                    )
                    _ANY_ITEM_CLIENTS.pop(space_id, None)
                    if not transient or attempt >= 2:
                        break
                    time.sleep(4 * attempt)

        try:
            if progress_cb:
                progress_cb(f"Falling back to {QWEN_EDIT_SPACE_ID}")
            return qwen_reference_try_on(
                str(person_path),
                str(object_path),
                object_class,
                int(seed),
                layer=layer,
            )
        except Exception as exc:
            errors.append(f"{QWEN_EDIT_SPACE_ID}={type(exc).__name__}:{exc}"[:700])

        try:
            if progress_cb:
                progress_cb("Falling back to Hugging Face Inference Provider")
            return inference_provider_reference_try_on(
                str(person_path),
                str(object_path),
                object_class,
                int(seed),
                layer=layer,
            )
        except Exception as exc:
            errors.append(f"inference-providers={type(exc).__name__}:{exc}"[:1200])

        detail = " | ".join(errors)
        quota_exhausted = any(
            marker in detail.lower()
            for marker in (
                "zerogpu runs limit",
                "exceeded your zerogpu",
                "quota",
                "rate limit",
            )
        )
        code = "any_item_provider_quota_exhausted" if quota_exhausted else "any_item_provider_failed"
        auth_hint = " (HF_TOKEN not configured)" if quota_exhausted and not HF_TOKEN else ""
        raise RuntimeError(f"{code}{auth_hint}: {detail}")
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


def set_progress(
    path: Path,
    job: dict[str, Any],
    stage: str,
    message: str | None = None,
) -> None:
    job["progress"] = {
        "stage": stage,
        "heartbeatAt": utc_now(),
        "message": message,
    }
    atomic_write(path, job)
    update_current(job)


def public_asset_path(job_id: str) -> str:
    return f"/dashboard/api/wardrobe/tryon/assets/{job_id}"


def outfit_cache_key(job: dict[str, Any], rendered_layers: list[str]) -> str:
    selected = job.get("input", {}).get("selectedLayers", {})
    uses_any_item = any(layer in ANY_ITEM_SUPPORTED for layer in rendered_layers)
    signature = {
        "schema": "agentos.tryon-cache/v1",
        "characterId": job.get("characterId"),
        "characterVersion": job.get("characterVersion"),
        "view": job.get("view", "front"),
        "pose": job.get("pose", "neutral_standing"),
        "renderer": "idm-vton+inference-provider-fallback/v5" if uses_any_item else "idm-vton-gradio-client/v1",
        "layers": [
            {
                "layer": layer,
                "garmentId": (selected.get(layer) or {}).get("garmentId"),
            }
            for layer in rendered_layers
        ],
    }
    raw = json.dumps(signature, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.webp"


def cache_meta_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.json"


def cached_render(job: dict[str, Any], rendered_layers: list[str]) -> tuple[str, Path] | None:
    key = outfit_cache_key(job, rendered_layers)
    cached = cache_path(key)
    meta = read_json(cache_meta_path(key))
    if not cached.exists() or cached.stat().st_size < 1000:
        return None
    # Legacy image-only cache entries are intentionally untrusted. Reuse is
    # allowed only after a separate visual QC step explicitly approves it.
    if not meta or meta.get("qualityAccepted") is not True:
        return None
    if meta.get("cacheKey") != key:
        return None
    return key, cached


def longest_cached_prefix(
    job: dict[str, Any],
    target_layers: list[str],
) -> tuple[list[str], str | None, Path | None]:
    # Only reuse a prefix of the canonical render order. Reusing an arbitrary
    # subset could bake layers in the wrong order and make later passes lie
    # about the visual result.
    for end in range(len(target_layers) - 1, 0, -1):
        prefix = target_layers[:end]
        hit = cached_render(job, prefix)
        if hit is not None:
            key, cached = hit
            return prefix, key, cached
    return [], None, None


def restore_cached_render(job: dict[str, Any], rendered_layers: list[str], target: Path) -> bool:
    hit = cached_render(job, rendered_layers)
    if hit is None:
        return False
    key, cached = hit
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(cached, target)
    os.chmod(target, 0o600)
    meta = read_json(cache_meta_path(key)) or {}
    job["output"] = {
        "asset": public_asset_path(job["jobId"]),
        "previewAsset": public_asset_path(job["jobId"]),
        "width": None,
        "height": None,
        "provider": "real-render-cache",
        "cacheKey": key,
        "renderedLayers": rendered_layers,
        "pendingLayers": [],
        "quality": {
            "state": "verified",
            "accepted": True,
            "checkedAt": meta.get("checkedAt"),
            "reviewer": meta.get("reviewer"),
            "receiptSchema": "agentos.wardrobe-visual-review-receipt/v1",
            "verifiedLayers": rendered_layers,
            "checks": meta.get("checks", []),
        },
    }
    return True


def persist_render_cache(job: dict[str, Any], rendered_layers: list[str], source: Path) -> str:
    key = outfit_cache_key(job, rendered_layers)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = cache_path(key)
    existing_meta = read_json(cache_meta_path(key)) or {}
    # A quality-approved cache is immutable. A provisional/rejected cache must
    # be replaced by the newest render for the same outfit signature.
    if not cached.exists() or existing_meta.get("qualityAccepted") is not True:
        tmp = cached.with_suffix(".webp.tmp")
        shutil.copyfile(source, tmp)
        os.chmod(tmp, 0o600)
        tmp.replace(cached)
    # Generated output is provisional until visual QC confirms there is no
    # missing selected garment and no stray reference/product object.
    atomic_write(
        cache_meta_path(key),
        {
            "schema": "agentos.tryon-cache-meta/v1",
            "cacheKey": key,
            "createdAt": utc_now(),
            "qualityAccepted": False,
            "qualityState": "candidate",
            "checkedAt": None,
            "checks": [
                {
                    "code": "visual_qc_required",
                    "passed": False,
                    "message": "Awaiting visual validation for missing garments and stray reference objects.",
                }
            ],
            "renderedLayers": rendered_layers,
            "jobId": job.get("jobId"),
        },
    )
    return key


def process_job(path: Path, job: dict[str, Any]) -> None:
    job["status"] = "rendering"
    job["startedAt"] = utc_now()
    job["error"] = None
    set_progress(path, job, "preparing_assets", "Preparing selected garment references")

    selected = job.get("input", {}).get("selectedLayers", {})
    if not isinstance(selected, dict):
        raise RuntimeError("selectedLayers missing")

    target_layers = [
        layer
        for layer in ORDER
        if layer in selected and (layer in CLOTHING_SUPPORTED or layer in ANY_ITEM_SUPPORTED)
    ]
    if not target_layers:
        raise RuntimeError("No renderable wardrobe layers selected yet")

    target = ASSET_DIR / f"{job['jobId']}.webp"
    if restore_cached_render(job, target_layers, target):
        job["status"] = "ready"
        job["completedAt"] = utc_now()
        job["failedAt"] = None
        set_progress(path, job, "ready", "Quality-approved cached render reused")
        return

    # Each successful pass uses the previous output as the next person image.
    # If an earlier outfit is an exact prefix of this new one, reuse its real
    # cached render and only compute the newly added layers. This is especially
    # important for quota-bound any-item providers such as shoes and bags.
    person_url = BASE_BODY_URL
    seed_base = abs(hash(job["jobId"])) % 100000
    provider_outputs: list[dict[str, Any]] = []
    rendered_layers: list[str] = []
    pending_layers: list[str] = []
    warnings: list[dict[str, str]] = []

    prefix_layers, prefix_cache_key, prefix_cache_path = longest_cached_prefix(job, target_layers)
    start_index = 0
    if prefix_cache_path is not None:
        person_url = str(prefix_cache_path)
        rendered_layers.extend(prefix_layers)
        start_index = len(prefix_layers)
        provider_outputs.append(
            {
                "layer": "+".join(prefix_layers),
                "provider": "real-render-cache-prefix",
                "providerSpace": "local-cache",
                "output": str(prefix_cache_path),
            }
        )

    for index, layer in enumerate(target_layers[start_index:], start=start_index):
        set_progress(
            path,
            job,
            "rendering",
            f"Rendering {layer} ({index + 1}/{len(target_layers)})",
        )
        item = selected[layer]
        source_url = item.get("sourceImageUrl") if isinstance(item, dict) else None
        if not isinstance(source_url, str) or not source_url.startswith(("http://", "https://")):
            pending_layers.append(layer)
            warnings.append({"layer": layer, "code": "missing_source_image"})
            continue

        previous_handler = signal.signal(signal.SIGALRM, _layer_timeout_handler)
        signal.alarm(max(1, LAYER_TIMEOUT_SECONDS))
        try:
            if layer in CLOTHING_SUPPORTED:
                garment_name = str(item.get("name") or "garment") if isinstance(item, dict) else "garment"
                description = f"{garment_name}; {CLOTHING_SUPPORTED[layer]}"
                try:
                    set_progress(path, job, "rendering", f"Rendering {layer} with {SPACE_ID}")
                    person_url = idm_try_on(person_url, source_url, description, seed_base + index, layer)
                    provider = "idm-vton-gradio-client"
                    provider_space = SPACE_ID
                except Exception as primary_exc:
                    set_progress(path, job, "rendering", f"{SPACE_ID} unavailable; trying Inference Provider fallback")
                    person_url, provider_space = inference_provider_reference_try_on(
                        person_url,
                        source_url,
                        CLOTHING_SUPPORTED[layer],
                        seed_base + index,
                        layer=layer,
                    )
                    provider = "hf-inference-provider-reference-edit"
                    warnings.append(
                        {
                            "layer": layer,
                            "code": "specialized_renderer_fallback",
                            "message": f"{type(primary_exc).__name__}: {primary_exc}"[:700],
                        }
                    )
            else:
                def any_item_progress(message: str):
                    set_progress(path, job, "rendering", f"{layer}: {message}")
                person_url, provider_space = omni_try_on(
                    person_url,
                    source_url,
                    ANY_ITEM_SUPPORTED[layer],
                    seed_base + index,
                    progress_cb=any_item_progress,
                    layer=layer,
                )
                provider = (
                    "qwen-image-2.1-reference-edit"
                    if provider_space == QWEN_EDIT_SPACE_ID
                    else "omnitry-gradio-client"
                )

            rendered_layers.append(layer)
            provider_outputs.append(
                {
                    "layer": layer,
                    "provider": provider,
                    "providerSpace": provider_space,
                    "output": person_url,
                }
            )
        except Exception as exc:
            pending_layers.append(layer)
            error_message = f"{type(exc).__name__}: {exc}"
            if len(error_message) > 900:
                error_message = error_message[:300] + " ... [tail] ... " + error_message[-580:]
            warnings.append(
                {
                    "layer": layer,
                    "code": "layer_renderer_failed",
                    "message": error_message,
                }
            )
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous_handler)

    if not rendered_layers:
        detail = "; ".join(
            f"{row.get('layer')}:{row.get('message') or row.get('code')}"
            for row in warnings
        )
        failure = f"No selected layer could be rendered: {detail}"
        if len(failure) > 1600:
            failure = failure[:500] + " ... [tail] ... " + failure[-1080:]
        raise RuntimeError(failure)

    set_progress(path, job, "validating", "Checking render completeness before publishing")
    copy_output(person_url, target)
    cache_key = None
    if not pending_layers:
        cache_key = persist_render_cache(job, target_layers, target)

    job["status"] = "ready"
    job["completedAt"] = utc_now()
    job["failedAt"] = None
    only_prefix_reused = bool(prefix_layers) and rendered_layers == prefix_layers
    job["output"] = {
        "asset": public_asset_path(job["jobId"]),
        "previewAsset": public_asset_path(job["jobId"]),
        "width": None,
        "height": None,
        "provider": "real-render-cache-prefix" if only_prefix_reused else "hybrid-vton",
        "providerOutputs": provider_outputs,
        "renderedLayers": rendered_layers,
        "pendingLayers": pending_layers,
        "warnings": warnings,
        "cacheKey": cache_key,
        "prefixCacheKey": prefix_cache_key,
        "quality": {
            "state": "candidate",
            "accepted": False,
            "checkedAt": None,
            "reviewer": None,
            "receiptSchema": "agentos.wardrobe-visual-review-receipt/v1",
            "verifiedLayers": [],
            "checks": [
                {
                    "code": "all_requested_layers_rendered",
                    "passed": len(pending_layers) == 0,
                    "message": None if not pending_layers else "Pending layers: " + ",".join(pending_layers),
                },
                {
                    "code": "visual_qc_required",
                    "passed": False,
                    "message": "Must detect missing garment or stray product/reference objects before cache reuse.",
                },
            ],
        },
    }
    set_progress(path, job, "ready", "Candidate render produced; visual review required before promotion")


def mark_failed(path: Path, job: dict[str, Any], exc: Exception) -> None:
    job["status"] = "failed"
    job["failedAt"] = utc_now()
    job["error"] = {
        "code": "renderer_failed",
        "message": f"{type(exc).__name__}: {exc}"[:1000],
    }
    set_progress(path, job, "failed", job["error"]["message"])


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
