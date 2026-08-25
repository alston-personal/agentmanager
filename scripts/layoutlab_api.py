#!/usr/bin/env python3
from __future__ import annotations

import argparse
import cgi
import json
import os
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

LAYOUTLIB_ROOT = Path(os.environ.get("LAYOUTLIB_ROOT", "/home/agentos-node/projects/layoutlib"))
if str(LAYOUTLIB_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(LAYOUTLIB_ROOT / "src"))

from layoutlib import parse_floorplan  # type: ignore  # noqa: E402

MAX_BODY = 12 * 1024 * 1024
ALLOWED_SUFFIXES = {".pgm", ".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def _scalar(params: dict[str, object], key: str, default: object) -> object:
    value = params.get(key, default)
    if isinstance(value, list):
        return value[0] if value else default
    return value


def _float(params: dict[str, object], key: str, default: float, lo: float, hi: float) -> float:
    try:
        value = float(_scalar(params, key, default))
    except Exception:
        value = default
    if not lo <= value <= hi:
        raise ValueError(f"{key} must be between {lo} and {hi}")
    return value


def _int(params: dict[str, object], key: str, default: int, lo: int, hi: int) -> int:
    try:
        value = int(_scalar(params, key, default))
    except Exception:
        value = default
    if not lo <= value <= hi:
        raise ValueError(f"{key} must be between {lo} and {hi}")
    return value


def parse_image_bytes(body: bytes, filename: str, params: dict[str, object]) -> dict:
    suffix = Path(filename or "upload.pgm").suffix.lower() or ".pgm"
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError("supported formats: PGM, PNG, JPG/JPEG, WEBP, BMP")
    if not body:
        raise ValueError("image is empty")

    scale = _float(params, "meters_per_pixel", 0.02, 0.0001, 10.0)
    height = _float(params, "wall_height_m", 2.7, 0.5, 20.0)
    threshold = _int(params, "threshold", 128, 0, 255)
    min_length = _int(params, "min_wall_length_px", 16, 2, 5000)
    max_thickness = _int(params, "max_wall_thickness_px", 16, 1, 512)

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(body)
        temp = Path(f.name)
    try:
        ir = parse_floorplan(
            temp,
            meters_per_pixel=scale,
            threshold=threshold,
            min_wall_length_px=min_length,
            max_wall_thickness_px=max_thickness,
            wall_height_m=height,
        )
        return {
            "ok": True,
            "engine": "layoutlib",
            "engine_version": getattr(__import__("layoutlib"), "__version__", "unknown"),
            "ir": ir.to_dict(),
            "warnings": [
                "v0.1 targets high-contrast, mostly orthogonal floor plans.",
                "Detected wall geometry is not a structural/load-bearing determination.",
            ],
        }
    finally:
        temp.unlink(missing_ok=True)


def _multipart(handler: BaseHTTPRequestHandler, length: int) -> tuple[bytes, str, dict[str, object]]:
    form = cgi.FieldStorage(
        fp=handler.rfile,
        headers=handler.headers,
        environ={
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": handler.headers.get("Content-Type", ""),
            "CONTENT_LENGTH": str(length),
        },
        keep_blank_values=True,
    )
    image = form["image"] if "image" in form else None
    if image is None or not getattr(image, "file", None):
        raise ValueError("multipart field 'image' is required")
    raw = image.file.read(MAX_BODY + 1)
    if len(raw) > MAX_BODY:
        raise ValueError(f"image must be <= {MAX_BODY} bytes")
    filename = Path(getattr(image, "filename", "") or "upload.pgm").name
    params: dict[str, object] = {}
    for key in ("meters_per_pixel", "wall_height_m", "threshold", "min_wall_length_px", "max_wall_thickness_px"):
        if key in form:
            params[key] = form.getfirst(key)
    return raw, filename, params


class Handler(BaseHTTPRequestHandler):
    server_version = "LayoutLabAPI/0.2"

    def _json(self, status: int, payload: dict):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/")
        if path in ("", "/healthz", "/layout-lab/api/healthz"):
            self._json(200, {"ok": True, "service": "layoutlab-api", "api_version": "0.2", "layoutlib_root": str(LAYOUTLIB_ROOT)})
        else:
            self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path.rstrip("/") not in ("/parse", "/layout-lab/api/parse"):
            self._json(404, {"ok": False, "error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY + 256 * 1024:
                raise ValueError(f"request body is outside the allowed size")
            content_type = self.headers.get("Content-Type", "")
            if content_type.lower().startswith("multipart/form-data"):
                body, filename, params = _multipart(self, length)
            else:
                body = self.rfile.read(length)
                params = {k: v for k, v in parse_qs(parsed.query).items()}
                filename = self.headers.get("X-Filename", "upload.pgm")
            self._json(200, parse_image_bytes(body, filename, params))
        except ValueError as exc:
            self._json(400, {"ok": False, "error": str(exc)})
        except Exception as exc:
            self._json(500, {"ok": False, "error": f"layoutlib parse failed: {exc}"})

    def log_message(self, fmt, *args):
        sys.stderr.write("layoutlab-api: " + fmt % args + "\n")


def main() -> int:
    p = argparse.ArgumentParser(description="Layout Lab API backed by LayoutLib")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", "0")))
    args = p.parse_args()
    if not args.port:
        raise SystemExit("--port or PORT is required; allocate it through AgentOS Port Manager")
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(json.dumps({"service":"layoutlab-api","api_version":"0.2","host":args.host,"port":args.port,"layoutlib_root":str(LAYOUTLIB_ROOT)}), flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
